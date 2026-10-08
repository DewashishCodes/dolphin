"""
Dolphin Hooks
==============
Thin client that agent hooks run on every session start, prompt and response.
It only talks to the local Dolphin daemon, so it must stay fast and must never
get in the agent's way: every failure is swallowed and the exit code is always 0.

Standard library only, and no imports from dolphin_memory beyond scopes.

Usage (Claude Code hooks):
    dolphin hook session-start        # prints a project memory brief
    dolphin hook user-prompt-submit   # prints memories relevant to the prompt
    dolphin hook stop                 # queues the exchange for capture

Set DOLPHIN_DISABLE=1 to turn the hooks off, or DOLPHIN_CAPTURE=0 to keep recall
but stop capturing.
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
from typing import Any, Dict, Optional

from dolphin_memory.scopes import project_scope

HOME = os.path.expanduser(os.environ.get("DOLPHIN_HOME", "~/.dolphin"))
STATE_FILE = os.path.join(HOME, "daemon.json")
DEFAULT_PORT = 47800

# The daemon is on this machine: never route through a system proxy
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# Prompts shorter than this ("yes", "continue") carry nothing to recall against
MIN_PROMPT_CHARS = 12


def read_state() -> Optional[Dict[str, Any]]:
    """The running daemon's port and token, if it has written them."""
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def health(timeout: float = 0.5) -> Optional[Dict[str, Any]]:
    """The daemon's health info, or None if it is not reachable."""
    state = read_state()
    if not state:
        return None
    try:
        url = f"http://127.0.0.1:{state['port']}/health"
        with _OPENER.open(url, timeout=timeout) as response:
            return json.load(response)
    except (OSError, ValueError, KeyError):
        return None


def request(path: str, payload: Dict[str, Any], timeout: float = 2.5) -> Optional[Dict[str, Any]]:
    """POST to the daemon. Returns None on any failure."""
    state = read_state()
    if not state:
        return None
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{state['port']}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Dolphin-Token": state["token"],
            },
        )
        with _OPENER.open(req, timeout=timeout) as response:
            return json.load(response)
    except (OSError, ValueError, KeyError):
        return None


def spawn_daemon() -> None:
    """Start the daemon as a background process that outlives this one."""
    command = [sys.executable, "-m", "dolphin_memory.daemon"]
    options: Dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            # Leave the caller's job object, so the daemon survives the hook
            subprocess.Popen(
                command, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **options
            )
        except OSError:
            subprocess.Popen(command, creationflags=flags, **options)
    else:
        subprocess.Popen(command, start_new_session=True, **options)


def ensure_daemon(wait: float = 0) -> bool:
    """Start the daemon if needed. Waits up to `wait` seconds for it to answer."""
    if health():
        return True
    try:
        spawn_daemon()
    except OSError:
        return False

    deadline = time.time() + wait
    while time.time() < deadline:
        time.sleep(0.2)
        if health():
            return True
    return False


# -----------------------------------------------------------------------------
# Hook events
# -----------------------------------------------------------------------------

def session_start(event: Dict[str, Any]) -> None:
    if not ensure_daemon(wait=6):
        return
    result = request("/brief", {"scope": project_scope(event.get("cwd"))})
    if result and result.get("context"):
        print(result["context"])


def user_prompt_submit(event: Dict[str, Any]) -> None:
    prompt = (event.get("prompt") or "").strip()
    if len(prompt) < MIN_PROMPT_CHARS or prompt.startswith("/"):
        return
    if not health():
        # Don't hold up the prompt; the daemon will be there for the next one
        ensure_daemon()
        return

    result = request("/recall", {
        "query": prompt,
        "scope": project_scope(event.get("cwd")),
        "session_id": event.get("session_id", ""),
    })
    if result and result.get("context"):
        print(result["context"])


def stop(event: Dict[str, Any]) -> None:
    if os.environ.get("DOLPHIN_CAPTURE", "1").lower() in ("0", "false", "off"):
        return
    response = event.get("last_assistant_message") or ""
    if not response:
        return
    request("/capture", {
        "scope": project_scope(event.get("cwd")),
        "session_id": event.get("session_id", ""),
        "response": response,
    })


EVENTS = {
    "session-start": session_start,
    "user-prompt-submit": user_prompt_submit,
    "stop": stop,
}


def main(argv) -> int:
    """`dolphin hook <event>`: reads the hook's JSON from stdin."""
    try:
        if os.environ.get("DOLPHIN_DISABLE", "").lower() in ("1", "true", "on"):
            return 0
        handler = EVENTS.get(argv[0] if argv else "")
        if handler is None:
            return 0
        # Hook JSON is UTF-8 whatever the console code page is
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        event = json.loads(raw) if raw.strip() else {}
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        handler(event)
    except Exception:
        # A memory problem must never block or break the agent
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
