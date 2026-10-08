"""
Supabase Backend
=================
Postgres + pgvector storage via Supabase. Requires the tables and functions
from schema.sql. Install with: pip install "dolphin-memory[supabase]"
"""

import logging
from typing import Optional, List, Dict, Any, Tuple

from dolphin_memory.backends.base import StorageBackend

logger = logging.getLogger("dolphin.store")


class SupabaseBackend(StorageBackend):
    """Stores memories and the graph in a Supabase project."""

    def __init__(self, url: str, key: str):
        try:
            from supabase import create_client
        except ImportError as e:
            raise ImportError(
                "The Supabase backend needs the 'supabase' package. "
                'Run: pip install "dolphin-memory[supabase]"'
            ) from e

        self.supabase = create_client(url, key)
        logger.info("Supabase client connected")

    # -------------------------------------------------------------------------
    # Memories
    # -------------------------------------------------------------------------

    def add_memory(self, session_id, memory_type, content, confidence, embedding):
        data = {
            "session_id": session_id,
            "memory_type": memory_type,
            "content": content,
            "confidence": confidence,
            "embedding": embedding,
        }
        result = self.supabase.table("user_memories").insert(data).execute()
        return result.data[0].get("id") if result.data else None

    def search_memories(self, session_id, embedding, limit, threshold):
        response = self.supabase.rpc("match_memories", {
            "query_embedding": embedding,
            "match_threshold": threshold,
            "match_count": limit,
            "p_session_id": session_id,
        }).execute()
        return response.data if response.data else []

    def touch_memory(self, memory_id):
        self.supabase.table("user_memories") \
            .update({"last_accessed": "now()"}) \
            .eq("id", memory_id) \
            .execute()

    def list_memories(self, session_id, limit):
        result = self.supabase.table("user_memories") \
            .select("id, memory_type, content, confidence, created_at") \
            .eq("session_id", session_id) \
            .eq("status", "active") \
            .order("created_at", desc=True) \
            .limit(limit) \
            .execute()
        return result.data if result.data else []

    def delete_memory(self, memory_id):
        result = self.supabase.table("user_memories") \
            .delete().eq("id", memory_id).execute()
        return bool(result.data)

    def delete_all(self, session_id):
        counts = {"memories": 0, "nodes": 0, "edges": 0}

        result = self.supabase.table("user_memories") \
            .delete().eq("session_id", session_id).execute()
        counts["memories"] = len(result.data) if result.data else 0

        # Delete edges (must come before nodes due to FK)
        result = self.supabase.table("graph_edges") \
            .delete().eq("session_id", session_id).execute()
        counts["edges"] = len(result.data) if result.data else 0

        result = self.supabase.table("graph_nodes") \
            .delete().eq("session_id", session_id).execute()
        counts["nodes"] = len(result.data) if result.data else 0

        return counts

    # -------------------------------------------------------------------------
    # Graph nodes
    # -------------------------------------------------------------------------

    def get_node_id(self, session_id, name):
        res = self.supabase.table("graph_nodes") \
            .select("id").eq("session_id", session_id).eq("name", name).execute()
        return res.data[0]["id"] if res.data else None

    def insert_node(self, session_id, name, label, embedding):
        new = self.supabase.table("graph_nodes").insert({
            "session_id": session_id,
            "name": name,
            "label": label,
            "embedding": embedding,
        }).execute()
        return new.data[0]["id"] if new.data else None

    def match_nodes(self, session_id, embedding, limit, threshold):
        res = self.supabase.rpc("match_graph_nodes", {
            "query_embedding": embedding,
            "match_threshold": threshold,
            "match_count": limit,
            "p_session_id": session_id,
        }).execute()
        return res.data if res.data else []

    def list_nodes(self, session_id, limit, exclude_name=None, oldest_first=False):
        query = self.supabase.table("graph_nodes") \
            .select("id, name, label").eq("session_id", session_id)
        if exclude_name:
            query = query.neq("name", exclude_name)
        if oldest_first:
            query = query.order("created_at")
        return query.limit(limit).execute().data or []

    def rename_node(self, node_id, name):
        self.supabase.table("graph_nodes") \
            .update({"name": name}).eq("id", node_id).execute()

    def merge_node(self, keep_id, delete_id):
        self.supabase.table("graph_edges") \
            .update({"source_id": keep_id}).eq("source_id", delete_id).execute()
        self.supabase.table("graph_edges") \
            .update({"target_id": keep_id}).eq("target_id", delete_id).execute()
        self.supabase.table("graph_nodes") \
            .delete().eq("id", delete_id).execute()

    # -------------------------------------------------------------------------
    # Graph edges
    # -------------------------------------------------------------------------

    def upsert_edge(self, session_id, source_id, target_id, relationship):
        existing = self.supabase.table("graph_edges") \
            .select("id, access_count") \
            .eq("source_id", source_id).eq("target_id", target_id) \
            .eq("relationship", relationship) \
            .execute()

        if existing.data:
            edge = existing.data[0]
            count = edge.get("access_count", 1)
            self.supabase.table("graph_edges").update({
                "access_count": count + 1,
                "weight": min(1.0 + count * 0.1, 5.0),
            }).eq("id", edge["id"]).execute()
        else:
            self.supabase.table("graph_edges").insert({
                "session_id": session_id,
                "source_id": source_id,
                "target_id": target_id,
                "relationship": relationship,
            }).execute()

    _EDGE_SELECT = (
        "relationship, source:graph_nodes!graph_edges_source_id_fkey(name, label), "
        "target:graph_nodes!graph_edges_target_id_fkey(name, label)"
    )

    def edges_from(self, node_ids, limit):
        if not node_ids:
            return []
        res = self.supabase.table("graph_edges").select(self._EDGE_SELECT) \
            .in_("source_id", node_ids).limit(limit).execute()
        return [self._flatten_edge(e) for e in res.data or []]

    def edges_to(self, node_ids, limit):
        if not node_ids:
            return []
        res = self.supabase.table("graph_edges").select(self._EDGE_SELECT) \
            .in_("target_id", node_ids).limit(limit).execute()
        return [self._flatten_edge(e) for e in res.data or []]

    @staticmethod
    def _flatten_edge(edge: Dict[str, Any]) -> Dict[str, Any]:
        source = edge.get("source") or {}
        target = edge.get("target") or {}
        return {
            "relationship": edge["relationship"],
            "source_name": source.get("name", "?"),
            "source_label": source.get("label", "?"),
            "target_name": target.get("name", "?"),
            "target_label": target.get("label", "?"),
        }

    def list_edges(self, session_id, limit):
        res = self.supabase.table("graph_edges") \
            .select("source_id, target_id, relationship") \
            .eq("session_id", session_id).limit(limit).execute()
        return res.data or []

    def stats(self, session_id) -> Tuple[int, int]:
        n = self.supabase.table("graph_nodes") \
            .select("id", count="exact").eq("session_id", session_id).execute()
        e = self.supabase.table("graph_edges") \
            .select("id", count="exact").eq("session_id", session_id).execute()
        return n.count or 0, e.count or 0
