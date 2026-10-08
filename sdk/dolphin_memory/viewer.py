"""
Dolphin Graph Viewer
=====================
A read-only web view of the local SQLite store: the knowledge graph as an
interactive 3D force graph, plus the stored memories. It re-reads the database
every few seconds, so a fact stored by one agent session appears while you watch.

It listens on 127.0.0.1 only, never writes, and does not load the embedding model.

Usage:
    dolphin graph [--port N] [--no-open]
"""

import json
import os
import sqlite3
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from dolphin_memory.config import DolphinConfig

DEFAULT_VIEWER_PORT = 8765
MAX_NODES = 2000
MAX_EDGES = 5000
MAX_MEMORIES = 100

_PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "viewer.html")


class Store:
    """Read-only access to the Dolphin SQLite file."""

    def __init__(self, db_path: str):
        self.db_path = os.path.abspath(os.path.expanduser(db_path))

    def _connect(self) -> Optional[sqlite3.Connection]:
        # Never create the file: a viewer pointed at the wrong path should show nothing
        if not os.path.exists(self.db_path):
            return None
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return conn

    def scopes(self) -> List[Dict[str, Any]]:
        conn = self._connect()
        if conn is None:
            return []
        try:
            counts: Dict[str, Dict[str, Any]] = {}
            for key, table, where in (
                ("nodes", "graph_nodes", ""),
                ("edges", "graph_edges", ""),
                ("memories", "user_memories", " WHERE status = 'active'"),
            ):
                rows = conn.execute(
                    f"SELECT session_id, COUNT(*) AS c FROM {table}{where} GROUP BY session_id"
                ).fetchall()
                for row in rows:
                    entry = counts.setdefault(
                        row["session_id"],
                        {"scope": row["session_id"], "nodes": 0, "edges": 0, "memories": 0},
                    )
                    entry[key] = row["c"]
            return sorted(
                counts.values(), key=lambda s: (s["nodes"] + s["memories"]), reverse=True
            )
        except sqlite3.Error:
            return []
        finally:
            conn.close()

    def graph(self, scope: str) -> Dict[str, Any]:
        empty = {"nodes": [], "links": [], "memories": []}
        conn = self._connect()
        if conn is None:
            return empty
        try:
            nodes = [
                dict(r) for r in conn.execute(
                    "SELECT id, name, label, access_count, created_at FROM graph_nodes "
                    "WHERE session_id = ? ORDER BY created_at LIMIT ?",
                    (scope, MAX_NODES),
                )
            ]
            ids = {n["id"] for n in nodes}
            links = [
                dict(r) for r in conn.execute(
                    "SELECT source_id AS source, target_id AS target, relationship, "
                    "weight FROM graph_edges WHERE session_id = ? LIMIT ?",
                    (scope, MAX_EDGES),
                )
                # Edges to nodes cut off by MAX_NODES would break the force graph
                if r["source"] in ids and r["target"] in ids
            ]
            memories = []
            for r in conn.execute(
                "SELECT id, memory_type, content, created_at FROM user_memories "
                "WHERE session_id = ? AND status = 'active' "
                "ORDER BY created_at DESC, id DESC LIMIT ?",
                (scope, MAX_MEMORIES),
            ):
                try:
                    content = json.loads(r["content"])
                except (TypeError, ValueError):
                    content = r["content"]
                value = content.get("value", "") if isinstance(content, dict) else str(content)
                memories.append({
                    "id": r["id"], "type": r["memory_type"],
                    "text": value, "created_at": r["created_at"],
                })
            return {"nodes": nodes, "links": links, "memories": memories}
        except sqlite3.Error:
            return empty
        finally:
            conn.close()


class _Handler(BaseHTTPRequestHandler):
    server: "ViewerServer"

    def log_message(self, format, *args):
        pass

    def _send(self, status: int, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: Any):
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json")

    def do_GET(self):
        # Refuse requests whose Host is not us, which blocks DNS-rebinding reads
        # of the memory from a web page the user happens to have open.
        port = self.server.server_address[1]
        if self.headers.get("Host", "") not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            self._json(403, {"error": "forbidden"})
            return

        url = urlparse(self.path)
        if url.path == "/":
            with open(_PAGE, "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif url.path == "/api/scopes":
            self._json(200, self.server.store.scopes())
        elif url.path == "/api/graph":
            scope = parse_qs(url.query).get("scope", [""])[0]
            if not scope:
                self._json(400, {"error": "missing scope"})
            else:
                self._json(200, self.server.store.graph(scope))
        else:
            self._json(404, {"error": "not found"})


class ViewerServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, port: int, store: Store):
        super().__init__(("127.0.0.1", port), _Handler)
        self.store = store


def main(argv: List[str]) -> int:
    """`dolphin graph [--port N] [--no-open]`"""
    port = int(os.environ.get("DOLPHIN_VIEWER_PORT", DEFAULT_VIEWER_PORT))
    open_browser = True

    args = list(argv)
    while args:
        arg = args.pop(0)
        if arg == "--no-open":
            open_browser = False
        elif arg == "--port" and args and args[0].isdigit():
            port = int(args.pop(0))
        else:
            print("Usage: dolphin graph [--port N] [--no-open]", file=sys.stderr)
            return 2

    config = DolphinConfig.from_env()
    if config.resolved_backend() != "sqlite":
        print(
            "The graph viewer reads the local SQLite store; this config uses Supabase. "
            "Set DOLPHIN_BACKEND=sqlite to view the local one.",
            file=sys.stderr,
        )
        return 1

    store = Store(config.db_path)
    try:
        server = ViewerServer(port, store)
    except OSError as e:
        print(f"Could not listen on port {port}: {e}. Try --port.", file=sys.stderr)
        return 1

    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Dolphin graph viewer: {url}")
    print(f"Reading {store.db_path}. Press Ctrl+C to stop.")
    if not os.path.exists(store.db_path):
        print("(No database yet; the page will fill in once memories are stored.)")
    if open_browser:
        threading.Timer(0.3, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
