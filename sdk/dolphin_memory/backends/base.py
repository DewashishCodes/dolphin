"""
Storage Backend Interface
==========================
Everything Dolphin persists goes through this interface, so the same memory
and graph logic runs on a local SQLite file or a Supabase project.

Embeddings are always computed by the caller and passed in as plain float lists.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Tuple


class StorageBackend(ABC):
    """Persistence layer for memories and the Knowledge Graph."""

    # -------------------------------------------------------------------------
    # Memories
    # -------------------------------------------------------------------------

    @abstractmethod
    def add_memory(
        self,
        session_id: str,
        memory_type: str,
        content: dict,
        confidence: float,
        embedding: List[float],
    ) -> Optional[int]:
        """Store a memory. Returns its id."""

    @abstractmethod
    def search_memories(
        self,
        session_id: str,
        embedding: List[float],
        limit: int,
        threshold: float,
    ) -> List[Dict[str, Any]]:
        """
        Active memories above the similarity threshold, best match first.
        Each dict has: id, memory_type, content, created_at, similarity.
        """

    @abstractmethod
    def touch_memory(self, memory_id: int) -> None:
        """Mark a memory as accessed just now."""

    @abstractmethod
    def list_memories(self, session_id: str, limit: int) -> List[Dict[str, Any]]:
        """Active memories, newest first."""

    @abstractmethod
    def delete_memory(self, memory_id: int) -> bool:
        """Delete one memory. Returns True if it existed."""

    @abstractmethod
    def delete_all(self, session_id: str) -> Dict[str, int]:
        """Delete all memories, nodes and edges for a session. Returns counts."""

    # -------------------------------------------------------------------------
    # Graph nodes
    # -------------------------------------------------------------------------

    @abstractmethod
    def get_node_id(self, session_id: str, name: str) -> Optional[str]:
        """Id of the node with this exact name, or None."""

    @abstractmethod
    def insert_node(
        self, session_id: str, name: str, label: str, embedding: List[float]
    ) -> Optional[str]:
        """Create a node. Returns its id."""

    @abstractmethod
    def match_nodes(
        self,
        session_id: str,
        embedding: List[float],
        limit: int,
        threshold: float,
    ) -> List[Dict[str, Any]]:
        """Nodes above the similarity threshold. Each dict has: id, name, label, similarity."""

    @abstractmethod
    def list_nodes(
        self,
        session_id: str,
        limit: int,
        exclude_name: Optional[str] = None,
        oldest_first: bool = False,
    ) -> List[Dict[str, Any]]:
        """Nodes for a session. Each dict has: id, name, label."""

    @abstractmethod
    def rename_node(self, node_id: str, name: str) -> None:
        """Change a node's name."""

    @abstractmethod
    def merge_node(self, keep_id: str, delete_id: str) -> None:
        """Re-point all edges of delete_id to keep_id, then delete delete_id."""

    # -------------------------------------------------------------------------
    # Graph edges
    # -------------------------------------------------------------------------

    @abstractmethod
    def upsert_edge(
        self, session_id: str, source_id: str, target_id: str, relationship: str
    ) -> None:
        """Create the edge, or reinforce it if the same triple already exists."""

    @abstractmethod
    def edges_from(self, node_ids: List[str], limit: int) -> List[Dict[str, Any]]:
        """
        Outgoing edges of the given nodes. Each dict has:
        relationship, source_name, source_label, target_name, target_label.
        """

    @abstractmethod
    def edges_to(self, node_ids: List[str], limit: int) -> List[Dict[str, Any]]:
        """Incoming edges of the given nodes. Same shape as edges_from."""

    @abstractmethod
    def list_edges(self, session_id: str, limit: int) -> List[Dict[str, Any]]:
        """Edges for a session. Each dict has: source_id, target_id, relationship."""

    @abstractmethod
    def stats(self, session_id: str) -> Tuple[int, int]:
        """(node count, edge count) for a session."""
