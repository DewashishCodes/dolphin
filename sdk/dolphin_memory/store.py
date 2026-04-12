"""
Memory Store
==============
Handles Supabase connection, embedding generation, and vector-based memory storage/retrieval.
This is the SDK's internal data layer — not exposed directly to users.
"""

import logging
import threading
from typing import Optional, List, Dict, Any

from supabase import create_client, Client
from dolphin_memory.config import DolphinConfig

logger = logging.getLogger("dolphin.store")


class MemoryStore:
    """Internal storage layer for Dolphin memories."""

    def __init__(self, config: DolphinConfig):
        self._config = config
        self._lock = threading.RLock()

        # Initialize Supabase client
        self.supabase: Client = create_client(config.supabase_url, config.supabase_key)
        logger.info("Supabase client connected")

        # Initialize embedding model (lazy — only when first needed)
        self._embeddings = None

    @property
    def embeddings(self):
        """Lazy-load the embedding model on first use (Thread-Safe)."""
        with self._lock:
            if self._embeddings is None:
                logger.info(f"Loading embedding model: {self._config.embedding_model}")
                from langchain_huggingface import HuggingFaceEmbeddings

            # Auto-detect GPU
            device = self._config.embedding_device
            if device == "auto":
                try:
                    import torch
                    device = "cuda" if torch.cuda.is_available() else "cpu"
                except ImportError:
                    device = "cpu"

            self._embeddings = HuggingFaceEmbeddings(
                model_name=self._config.embedding_model,
                model_kwargs={"device": device},
            )
            logger.info(f"Embedding model loaded on {device}")
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
    ) -> Optional[int]:
        """Store a structured memory with its embedding."""
        try:
            # Create a searchable text representation
            memory_string = f"{memory_type}: {content.get('key', '')} {content.get('value', '')}"
            vector = self.embed(memory_string)

            data = {
                "session_id": session_id,
                "memory_type": memory_type,
                "content": content,
                "confidence": confidence,
                "embedding": vector,
            }
            result = self.supabase.table("user_memories").insert(data).execute()

            if result.data:
                memory_id = result.data[0].get("id")
                logger.info(f"Memory stored: id={memory_id}, type={memory_type}")
                return memory_id
            return None
        except Exception as e:
            logger.error(f"Failed to store memory: {e}")
            raise

    def search_memories(
        self,
        session_id: str,
        query: str,
        limit: int = 5,
        threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Find semantically relevant memories using vector similarity."""
        try:
            query_vector = self.embed(query)
            rpc_params = {
                "query_embedding": query_vector,
                "match_threshold": threshold if threshold is not None else self._config.similarity_threshold,
                "match_count": limit,
                "p_session_id": session_id,
            }
            response = self.supabase.rpc("match_memories", rpc_params).execute()
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Memory search failed: {e}")
            return []

    def update_memory_access(self, memory_id: int):
        """Update the timestamp and reinforcement count for an existing memory."""
        try:
            # We don't have a count column in user_memories yet, just update last_accessed
            self.supabase.table("user_memories") \
                .update({"last_accessed": "now()"}) \
                .eq("id", memory_id) \
                .execute()
        except Exception as e:
            logger.warning(f"Failed to update memory access {memory_id}: {e}")

    def get_all(self, session_id: str, limit: int = 100) -> List[Dict]:
        """Get all memories for a session (no similarity search)."""
        try:
            result = self.supabase.table("user_memories") \
                .select("id, memory_type, content, confidence, created_at") \
                .eq("session_id", session_id) \
                .eq("status", "active") \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Failed to get memories: {e}")
            return []

    def delete_all(self, session_id: str) -> Dict[str, int]:
        """Delete all data for a session (memories, nodes, edges)."""
        counts = {"memories": 0, "nodes": 0, "edges": 0}
        try:
            # Delete memories
            result = self.supabase.table("user_memories") \
                .delete().eq("session_id", session_id).execute()
            counts["memories"] = len(result.data) if result.data else 0

            # Delete edges (must come before nodes due to FK)
            result = self.supabase.table("graph_edges") \
                .delete().eq("session_id", session_id).execute()
            counts["edges"] = len(result.data) if result.data else 0

            # Delete nodes
            result = self.supabase.table("graph_nodes") \
                .delete().eq("session_id", session_id).execute()
            counts["nodes"] = len(result.data) if result.data else 0

            logger.info(f"Deleted all data for {session_id}: {counts}")
            return counts
        except Exception as e:
            logger.error(f"Failed to delete data: {e}")
            raise
