"""
Dolphin Daemon
===============
One long-lived local process that keeps the embedding model loaded, so agent
hooks can recall and capture memory in milliseconds instead of loading a model
on every prompt.

It listens on 127.0.0.1 only and requires a token that is written to
~/.dolphin/daemon.json, so other users and web pages cannot read or write memory.

Usage:
    dolphin daemon start | stop | status
"""

import hmac
import json
import logging
import os
import secrets
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional

from dolphin_memory import __version__
from dolphin_memory.client import DolphinMemory
from dolphin_memory.config import DolphinConfig
from dolphin_memory.hook import STATE_FILE, HOME, DEFAULT_PORT, read_state, health
from dolphin_memory.scopes import USER_SCOPE

logger = logging.getLogger("dolphin.daemon")

# Automatic recall is stricter than search(): only inject what clearly relates.
# With the default MiniLM embedder, related prompts score roughly 0.27-0.6 against
# the right memory and unrelated ones stay at or below 0.2.
RECALL_THRESHOLD = 0.25
RECALL_LIMIT = 5
RECALL_MAX_CHARS = 1500
BRIEF_LIMIT = 8
CAPTURE_MAX_CHARS = 6000
IDLE_SHUTDOWN_SECONDS = float(os.environ.get("DOLPHIN_IDLE_HOURS", "8")) * 3600

RECALL_HEADER = (
    "[Dolphin memory: recalled from earlier sessions on this machine. It may be "
    "outdated; check it against the code before relying on it.]"
)


class MemoryService:
    """The operations hooks call, on top of one shared DolphinMemory."""

    def __init__(self, memory: DolphinMemory):
        self.memory = memory
        # Capture runs one at a time: local LLMs don't parallelize well
        self._capture_pool = ThreadPoolExecutor(max_workers=1)
        self._last_prompt: Dict[str, str] = {}
        self._lock = threading.Lock()

    def _lines(self, hits: List[Dict[str, Any]]) -> List[str]:
        lines = []
        for hit in hits:
            content = hit.get("content") or {}
            value = content.get("value", "") if isinstance(content, dict) else str(content)
            when = self.memory._get_relative_time(hit.get("created_at"))
            lines.append(f"- [{when}] {value}")
        return lines

    def recall(self, query: str, scope: str, session_id: str = "") -> str:
        """Context to inject ahead of a prompt. Empty when nothing clearly relates."""
        if session_id:
            with self._lock:
                self._last_prompt[session_id] = query

        sections = []
        for title, ns in (("Project memory", scope), ("Your preferences", USER_SCOPE)):
            hits = self.memory.search(
                query, scope=ns, limit=RECALL_LIMIT, threshold=RECALL_THRESHOLD
            )
            if hits:
                sections.append(f"{title}:\n" + "\n".join(self._lines(hits)))
        if not sections:
            return ""

        # Relationship facts only; skip the bare "Relevant:"/"Known:" node listings
        facts = [
            f"- {line}" for line in self.memory._graph.get_context(scope, query).splitlines()
            if line and not line.startswith(("Relevant:", "Known:"))
        ][:8]
        if facts:
            sections.append("Related facts:\n" + "\n".join(facts))

        text = RECALL_HEADER + "\n" + "\n".join(sections)
        return text[:RECALL_MAX_CHARS]

    def brief(self, scope: str) -> str:
        """A short summary of what memory holds for a project, for session start."""
        recent = self.memory.get_all_memories(scope=scope, limit=BRIEF_LIMIT)
        if not recent:
            return ""
        stats = self.memory.get_stats(scope=scope)
        return (
            f"{RECALL_HEADER}\n"
            f"Most recent project memories ({stats['nodes']} entities, "
            f"{stats['edges']} relationships in the knowledge graph):\n"
            + "\n".join(self._lines(recent))
            + "\nRelevant memories are added to each prompt automatically. Use the "
            "dolphin `recall` tool to look something up and `remember` to store a "
            "decision, convention or gotcha a future session would need."
        )

    def capture(self, scope: str, session_id: str, response: str) -> bool:
        """Queue the latest exchange of a session for distillation into memories."""
        with self._lock:
            prompt = self._last_prompt.pop(session_id, "")
        if not prompt or not response:
            return False

        exchange = f"Developer: {prompt}\n\nAgent: {response}"[:CAPTURE_MAX_CHARS]
        metadata = {"source": "claude-code", "session": session_id}
        self._capture_pool.submit(self._capture, exchange, scope, metadata)
        return True

    def _capture(self, exchange: str, scope: str, metadata: Dict[str, Any]):
        try:
            stored = self.memory.capture(exchange, scope=scope, metadata=metadata)
            if stored:
                logger.info(f"Captured {len(stored)} memories for {scope}")
        except Exception as e:
            logger.error(f"Capture failed: {e}", exc_info=True)


class _Handler(BaseHTTPRequestHandler):
    server: "DaemonServer"

    def log_message(self, format, *args):
        logger.debug(format % args)

    def _reply(self, status: int, body: Dict[str, Any]):
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self._reply(200, {"ok": True, "version": __version__, "pid": os.getpid()})
        else:
            self._reply(404, {"error": "not found"})

    def do_POST(self):
        self.server.last_request = time.time()

        token = self.headers.get("X-Dolphin-Token", "")
        if not hmac.compare_digest(token, self.server.token):
            self._reply(403, {"error": "forbidden"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._reply(400, {"error": "invalid JSON"})
            return

        service = self.server.service
        try:
            if self.path == "/recall":
                context = service.recall(
                    body["query"], body["scope"], body.get("session_id", "")
                )
                self._reply(200, {"context": context})
            elif self.path == "/brief":
                self._reply(200, {"context": service.brief(body["scope"])})
            elif self.path == "/capture":
                queued = service.capture(
                    body["scope"], body.get("session_id", ""), body.get("response", "")
                )
                self._reply(200, {"queued": queued})
            elif self.path == "/shutdown":
                self._reply(200, {"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                self._reply(404, {"error": "not found"})
        except KeyError as e:
            self._reply(400, {"error": f"missing field {e}"})
        except Exception as e:
            logger.error(f"{self.path} failed: {e}", exc_info=True)
            self._reply(500, {"error": str(e)})


class DaemonServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int, service: MemoryService):
        super().__init__(("127.0.0.1", port), _Handler)
        self.service = service
        self.token = secrets.token_urlsafe(32)
        self.last_request = time.time()


def _write_state(server: DaemonServer):
    os.makedirs(HOME, exist_ok=True)
    state = {
        "pid": os.getpid(),
        "port": server.server_address[1],
        "token": server.token,
        "version": __version__,
    }
    # Owner-only: the token grants access to memory
    fd = os.open(STATE_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(state, f)


def _remove_state():
    state = read_state()
    if state and state.get("pid") == os.getpid():
        try:
            os.remove(STATE_FILE)
        except OSError:
            pass


def _idle_watch(server: DaemonServer):
    while True:
        time.sleep(60)
        if time.time() - server.last_request > IDLE_SHUTDOWN_SECONDS:
            logger.info("Idle, shutting down")
            server.shutdown()
            return


def serve(memory: Optional[DolphinMemory] = None, port: Optional[int] = None) -> None:
    """Run the daemon in the foreground until it is stopped or goes idle."""
    if port is None:
        port = int(os.environ.get("DOLPHIN_PORT", DEFAULT_PORT))

    os.makedirs(HOME, exist_ok=True)
    logging.basicConfig(
        level=os.environ.get("DOLPHIN_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[logging.FileHandler(os.path.join(HOME, "daemon.log"), encoding="utf-8")],
        force=True,
    )

    if memory is None:
        memory = DolphinMemory(config=DolphinConfig.for_agents())

    try:
        server = DaemonServer(port, MemoryService(memory))
    except OSError as e:
        # Another daemon won the race for the port
        logger.info(f"Not starting: port {port} is unavailable ({e})")
        return

    _write_state(server)
    logger.info(f"Dolphin daemon {__version__} listening on 127.0.0.1:{port}")

    threading.Thread(target=memory.prewarm, daemon=True).start()
    threading.Thread(target=_idle_watch, args=(server,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        _remove_state()
        logger.info("Dolphin daemon stopped")


def main(argv: List[str]) -> int:
    """`dolphin daemon <start|stop|status|run>`"""
    from dolphin_memory.hook import ensure_daemon, request

    command = argv[0] if argv else "status"

    if command == "run":
        serve()
    elif command == "start":
        if ensure_daemon(wait=20):
            print(f"Dolphin daemon is running (pid {health()['pid']}).")
        else:
            print(f"Daemon did not start. See {os.path.join(HOME, 'daemon.log')}", file=sys.stderr)
            return 1
    elif command == "stop":
        if health() and request("/shutdown", {}) is not None:
            print("Dolphin daemon stopped.")
        else:
            print("Dolphin daemon is not running.")
    elif command == "status":
        info = health()
        if info:
            print(f"Running: pid {info['pid']}, version {info['version']}")
        else:
            print("Not running.")
    else:
        print("Usage: dolphin daemon start | stop | status", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    serve()
