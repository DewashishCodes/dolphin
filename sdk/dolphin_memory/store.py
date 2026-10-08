"""
Memory Store
==============
Handles embedding generation and vector-based memory storage/retrieval on top of
a storage backend (SQLite or Supabase).
This is the SDK's internal data layer — not exposed directly to users.
"""

import logging
import threading
from typing import Optional, List, Dict, Any

from dolphin_memory.backends import create_backend
from dolphin_memory.config import DolphinConfig
from dolphin_memory.embeddings import create_embedder

logger = logging.getLogger("dolphin.store")


class MemoryStore:
    """Internal storage layer for Dolphin memories."""

    def __init__(self, config: DolphinConfig):
        self._config = config
        self._lock = threading.RLock()

        self.backend = create_backend(config)

        # Vectors from different models can't share a local database
        if hasattr(self.backend, "check_embedding_model"):
            try:
                self.backend.check_embedding_model(config.resolved_embedding()[1])
            except ValueError:
                self.backend.close()
                raise

        # Initialize embedding model (lazy — only when first needed)
        self._embeddings = None

    @property
    def embeddings(self):
        """Lazy-load the embedding model on first use (Thread-Safe)."""
        with self._lock:
            if self._embeddings is None:
                self._embeddings = create_embedder(self._config)
        return self._embeddings

    def embed(self, text: str) -> List[float]:
        """Generate an embedding vector for the given text."""
        return self.embeddings.embed_query(text)

    # -------------------------------------------------------------------------
    # Memory CRUD
    # -------------------------------------------------------------------------

    def add_memory(
        self,
        session_id: str,
        memory_type: str,
        content: dict,
        confidence: float = 1.0,
        embedding: Optional[List[float]] = None,
    ) -> Optional[int]:
        """Store a structured memory with its embedding."""
        try:
            # Use raw value for embedding to ensure better semantic search matches
            if embedding is None:
                embedding = self.embed(content.get('value', str(content)))

            memory_id = self.backend.add_memory(
                session_id, memory_type, content, confidence, embedding
            )
            if memory_id is not None:
                logger.info(f"Memory stored: id={memory_id}, type={memory_type}")
            return memory_id
        except Exception as e:
            logger.error(f"Failed to store memory: {e}")
            raise

    def search_memories(
        self,
        session_id: str,
        query: str,
        limit: int = 5,
        threshold: Optional[float] = None,
        embedding: Optional[List[float]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find semantically relevant memories using vector similarity.
        Pass `embedding` to reuse a vector already computed for `query`.
        """
        try:
            if embedding is None:
                embedding = self.embed(query)
            if threshold is None:
                threshold = self._config.similarity_threshold
            return self.backend.search_memories(session_id, embedding, limit, threshold)
        except Exception as e:
            logger.error(f"Memory search failed: {e}")
            return []

    def update_memory_access(self, memory_id: int):
        """Update the last-accessed timestamp for an existing memory."""
        try:
            self.backend.touch_memory(memory_id)
        except Exception as e:
            logger.warning(f"Failed to update memory access {memory_id}: {e}")

    def get_all(self, session_id: str, limit: int = 100) -> List[Dict]:
        """Get all memories for a session (no similarity search)."""
        try:
            return self.backend.list_memories(session_id, limit)
        except Exception as e:
            logger.error(f"Failed to get memories: {e}")
            return []

    def delete_memory(self, memory_id: int) -> bool:
        """Delete a single memory by id."""
        try:
            return self.backend.delete_memory(memory_id)
        except Exception as e:
            logger.error(f"Failed to delete memory {memory_id}: {e}")
            raise

    def delete_all(self, session_id: str) -> Dict[str, int]:
        """Delete all data for a session (memories, nodes, edges)."""
        try:
            counts = self.backend.delete_all(session_id)
            logger.info(f"Deleted all data for {session_id}: {counts}")
            return counts
        except Exception as e:
            logger.error(f"Failed to delete data: {e}")
            raise
