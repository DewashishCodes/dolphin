"""
SQLite Backend
===============
Zero-setup local storage: one file, no server. This is the default backend and
the one local agents share. Vector search is exact cosine similarity over the
session's embeddings, which is fast at the scale of a personal or project memory.

WAL mode lets several processes (e.g. multiple agent sessions) read and write
the same file.
"""

import json
import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple

import numpy as np

from dolphin_memory.backends.base import StorageBackend

logger = logging.getLogger("dolphin.store")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    memory_type TEXT,
    content TEXT,
    confidence REAL DEFAULT 1.0,
    last_accessed TEXT,
    embedding BLOB,
    status TEXT DEFAULT 'active',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_nodes (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    name TEXT NOT NULL,
    label TEXT NOT NULL,
    embedding BLOB,
    access_count INTEGER DEFAULT 0,
    decay_score REAL DEFAULT 1.0,
    last_accessed TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (session_id, name)
);

CREATE TABLE IF NOT EXISTS graph_edges (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    source_id TEXT REFERENCES graph_nodes(id) ON DELETE CASCADE,
    target_id TEXT REFERENCES graph_nodes(id) ON DELETE CASCADE,
    relationship TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    last_accessed TEXT,
    access_count INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE (source_id, target_id, relationship)
);

CREATE TABLE IF NOT EXISTS dolphin_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_user_memories_session ON user_memories(session_id);
CREATE INDEX IF NOT EXISTS idx_graph_nodes_session ON graph_nodes(session_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_session ON graph_edges(session_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_source ON graph_edges(source_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_target ON graph_edges(target_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_blob(embedding: List[float]) -> bytes:
    return np.asarray(embedding, dtype=np.float32).tobytes()


class SQLiteBackend(StorageBackend):
    """Stores memories and the graph in a local SQLite file."""

    def __init__(self, db_path: str):
        self.db_path = os.path.abspath(os.path.expanduser(db_path))
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        with self._lock, self._conn:
            self._conn.executescript(_SCHEMA)
        logger.info(f"SQLite store ready: {self.db_path}")

    def close(self):
        with self._lock:
            self._conn.close()

    def check_embedding_model(self, model_name: str) -> None:
        """
        Record which embedding model wrote this database, and refuse to mix models:
        vectors from different models are not comparable.
        """
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT value FROM dolphin_meta WHERE key = 'embedding_model'"
            ).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO dolphin_meta (key, value) VALUES ('embedding_model', ?)",
                    (model_name,),
                )
            elif row["value"] != model_name:
                raise ValueError(
                    f"{self.db_path} was created with embedding model '{row['value']}', "
                    f"but this config uses '{model_name}'. Use the original model or a "
                    "different db_path."
                )

    # -------------------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------------------

    def _query(self, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock, self._conn:
            return self._conn.execute(sql, params)

    @staticmethod
    def _rank(
        rows: List[sqlite3.Row], embedding: List[float], limit: int, threshold: float
    ) -> List[Tuple[sqlite3.Row, float]]:
        """Score rows by cosine similarity to the query, keep those above threshold."""
        rows = [r for r in rows if r["embedding"]]
        if not rows:
            return []

        query = np.asarray(embedding, dtype=np.float32)
        matrix = np.frombuffer(b"".join(r["embedding"] for r in rows), dtype=np.float32)
        matrix = matrix.reshape(len(rows), -1)
        if matrix.shape[1] != query.shape[0]:
            logger.error(
                f"Embedding size mismatch: stored {matrix.shape[1]}, query {query.shape[0]}"
            )
            return []

        norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query)
        norms[norms == 0] = 1.0
        scores = (matrix @ query) / norms

        order = np.argsort(-scores)
        return [
            (rows[i], float(scores[i])) for i in order if scores[i] > threshold
        ][:limit]

    @staticmethod
    def _placeholders(items: List[Any]) -> str:
        return ",".join("?" * len(items))

    # -------------------------------------------------------------------------
    # Memories
    # -------------------------------------------------------------------------

    def add_memory(self, session_id, memory_type, content, confidence, embedding):
        cur = self._execute(
            "INSERT INTO user_memories "
            "(session_id, memory_type, content, confidence, embedding, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, memory_type, json.dumps(content), confidence,
             _to_blob(embedding), _now()),
        )
        return cur.lastrowid

    def search_memories(self, session_id, embedding, limit, threshold):
        rows = self._query(
            "SELECT id, memory_type, content, created_at, embedding FROM user_memories "
            "WHERE session_id = ? AND status = 'active'",
            (session_id,),
        )
        return [
            {
                "id": row["id"],
                "memory_type": row["memory_type"],
                "content": json.loads(row["content"]),
                "created_at": row["created_at"],
                "similarity": score,
            }
            for row, score in self._rank(rows, embedding, limit, threshold)
        ]

    def touch_memory(self, memory_id):
        self._execute(
            "UPDATE user_memories SET last_accessed = ? WHERE id = ?", (_now(), memory_id)
        )

    def list_memories(self, session_id, limit):
        rows = self._query(
            "SELECT id, memory_type, content, confidence, created_at FROM user_memories "
            "WHERE session_id = ? AND status = 'active' "
            "ORDER BY created_at DESC, id DESC LIMIT ?",
            (session_id, limit),
        )
        return [{**dict(r), "content": json.loads(r["content"])} for r in rows]

    def delete_memory(self, memory_id):
        cur = self._execute("DELETE FROM user_memories WHERE id = ?", (memory_id,))
        return cur.rowcount > 0

    def delete_all(self, session_id):
        counts = {}
        # Edges before nodes, so the counts are not hidden by the FK cascade
        for key, table in (
            ("memories", "user_memories"),
            ("edges", "graph_edges"),
            ("nodes", "graph_nodes"),
        ):
            cur = self._execute(f"DELETE FROM {table} WHERE session_id = ?", (session_id,))
            counts[key] = cur.rowcount
        return counts

    # -------------------------------------------------------------------------
    # Graph nodes
    # -------------------------------------------------------------------------

    def get_node_id(self, session_id, name):
        rows = self._query(
            "SELECT id FROM graph_nodes WHERE session_id = ? AND name = ?",
            (session_id, name),
        )
        return rows[0]["id"] if rows else None

    def insert_node(self, session_id, name, label, embedding):
        node_id = str(uuid.uuid4())
        now = _now()
        # Another session may have created the same node since the caller looked
        self._execute(
            "INSERT OR IGNORE INTO graph_nodes "
            "(id, session_id, name, label, embedding, last_accessed, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (node_id, session_id, name, label, _to_blob(embedding), now, now),
        )
        return self.get_node_id(session_id, name)

    def match_nodes(self, session_id, embedding, limit, threshold):
        rows = self._query(
            "SELECT id, name, label, embedding FROM graph_nodes WHERE session_id = ?",
            (session_id,),
        )
        return [
            {"id": row["id"], "name": row["name"], "label": row["label"], "similarity": score}
            for row, score in self._rank(rows, embedding, limit, threshold)
        ]

    def list_nodes(self, session_id, limit, exclude_name=None, oldest_first=False):
        sql = "SELECT id, name, label FROM graph_nodes WHERE session_id = ?"
        params: List[Any] = [session_id]
        if exclude_name:
            sql += " AND name != ?"
            params.append(exclude_name)
        if oldest_first:
            sql += " ORDER BY created_at"
        sql += " LIMIT ?"
        params.append(limit)
        return [dict(r) for r in self._query(sql, tuple(params))]

    def rename_node(self, node_id, name):
        self._execute("UPDATE graph_nodes SET name = ? WHERE id = ?", (name, node_id))

    def merge_node(self, keep_id, delete_id):
        with self._lock, self._conn:
            # OR IGNORE: an edge that already exists on keep_id stays as it is, and
            # the duplicate goes away with the deleted node via the FK cascade.
            self._conn.execute(
                "UPDATE OR IGNORE graph_edges SET source_id = ? WHERE source_id = ?",
                (keep_id, delete_id),
            )
            self._conn.execute(
                "UPDATE OR IGNORE graph_edges SET target_id = ? WHERE target_id = ?",
                (keep_id, delete_id),
            )
            self._conn.execute("DELETE FROM graph_nodes WHERE id = ?", (delete_id,))

    # -------------------------------------------------------------------------
    # Graph edges
    # -------------------------------------------------------------------------

    def upsert_edge(self, session_id, source_id, target_id, relationship):
        now = _now()
        self._execute(
            "INSERT INTO graph_edges "
            "(id, session_id, source_id, target_id, relationship, last_accessed, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (source_id, target_id, relationship) DO UPDATE SET "
            "weight = MIN(1.0 + access_count * 0.1, 5.0), "
            "access_count = access_count + 1, "
            "last_accessed = excluded.last_accessed",
            (str(uuid.uuid4()), session_id, source_id, target_id, relationship, now, now),
        )

    _EDGE_SELECT = (
        "SELECT e.relationship, s.name AS source_name, s.label AS source_label, "
        "t.name AS target_name, t.label AS target_label "
        "FROM graph_edges e "
        "JOIN graph_nodes s ON s.id = e.source_id "
        "JOIN graph_nodes t ON t.id = e.target_id "
    )

    def edges_from(self, node_ids, limit):
        if not node_ids:
            return []
        rows = self._query(
            self._EDGE_SELECT
            + f"WHERE e.source_id IN ({self._placeholders(node_ids)}) LIMIT ?",
            (*node_ids, limit),
        )
        return [dict(r) for r in rows]

    def edges_to(self, node_ids, limit):
        if not node_ids:
            return []
        rows = self._query(
            self._EDGE_SELECT
            + f"WHERE e.target_id IN ({self._placeholders(node_ids)}) LIMIT ?",
            (*node_ids, limit),
        )
        return [dict(r) for r in rows]

    def list_edges(self, session_id, limit):
        rows = self._query(
            "SELECT source_id, target_id, relationship FROM graph_edges "
            "WHERE session_id = ? LIMIT ?",
            (session_id, limit),
        )
        return [dict(r) for r in rows]

    def stats(self, session_id) -> Tuple[int, int]:
        n = self._query(
            "SELECT COUNT(*) AS c FROM graph_nodes WHERE session_id = ?", (session_id,)
        )[0]["c"]
        e = self._query(
            "SELECT COUNT(*) AS c FROM graph_edges WHERE session_id = ?", (session_id,)
        )[0]["c"]
        return n, e
