"""
Dolphin Memory Client
======================
The main public API. One class, clean interface, works in 5 minutes.

Usage:
    from dolphin_memory import DolphinMemory

    memory = DolphinMemory(
        supabase_url="https://your-project.supabase.co",
        supabase_key="your-anon-key",
    )

    memory.add("I love Python and live in Mumbai", user_id="user_123")
    results = memory.search("programming languages", user_id="user_123")
    context = memory.get_context("Tell me about the user", user_id="user_123")
"""

import logging
from typing import Optional, List, Dict, Any

from dolphin_memory.config import DolphinConfig
from dolphin_memory.store import MemoryStore
from dolphin_memory.graph import GraphEngine
from dolphin_memory.extraction import TripleExtractor

logger = logging.getLogger("dolphin")


class DolphinMemory:
    """
    🐬 Give your AI a brain.

    DolphinMemory provides persistent, graph-enhanced memory for any LLM application.
    It combines vector similarity search with a Knowledge Graph for deep,
    structured recall.

    Args:
        supabase_url: Your Supabase project URL
        supabase_key: Your Supabase anon/service key
        config: Optional DolphinConfig for advanced settings
        **kwargs: Any DolphinConfig parameter can be passed directly

    Example:
        >>> from dolphin_memory import DolphinMemory
        >>> memory = DolphinMemory(
        ...     supabase_url="https://abc.supabase.co",
        ...     supabase_key="your-key",
        ... )
        >>> memory.add("User loves Python", user_id="u1")
        >>> memory.search("programming", user_id="u1")
    """

    def __init__(
        self,
        supabase_url: str = "",
        supabase_key: str = "",
        config: Optional[DolphinConfig] = None,
        **kwargs
    ):
        # Build config from arguments
        if config:
            self._config = config
        else:
            self._config = DolphinConfig(
                supabase_url=supabase_url,
                supabase_key=supabase_key,
                **kwargs
            )
        self._config.validate()

        # Initialize internal components
        self._store = MemoryStore(self._config)
        self._graph = GraphEngine(self._store, self._config)
        self._extractor = TripleExtractor(self._config)

        logger.info("🐬 Dolphin Memory initialized")

    # -------------------------------------------------------------------------
    # Core API: add, search, get_context
    # -------------------------------------------------------------------------

    def add(
        self,
        text: str,
        user_id: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Add a memory. Dolphin will:
        1. Store the raw text with its embedding (for semantic search)
        2. Extract entities & relationships into the Knowledge Graph

        Args:
            text: The memory content (e.g., "I live in Mumbai and work at Google")
            user_id: User namespace — isolates memories per user
            metadata: Optional metadata dict to store alongside the memory

        Returns:
            Dict with 'memory_id' and 'triples' (extracted graph relationships)

        Example:
            >>> memory.add("I live in Mumbai and love Python", user_id="u1")
            {'memory_id': 42, 'triples': [{'s': 'User', 'p': 'LIVES_IN', 'o': 'Mumbai'}]}
        """
        session_id = f"user_{user_id}"

        # 1. Store as a structured memory with embedding
        memory_data = {
            "key": "user_input",
            "value": text,
        }
        if metadata:
            memory_data.update(metadata)

        memory_id = self._store.add_memory(
            session_id=session_id,
            memory_type="conversation",
            content=memory_data,
            confidence=1.0,
        )

        # 2. Extract and sync graph triples (if auto_extract is on)
        triples = []
        if self._config.auto_extract:
            triples = self._graph.extract_and_sync(session_id, text)

        return {
            "memory_id": memory_id,
            "triples": triples,
        }

    def search(
        self,
        query: str,
        user_id: str = "default",
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Search memories by semantic similarity.

        Args:
            query: Natural language search query
            user_id: User namespace to search within
            limit: Maximum number of results

        Returns:
            List of matching memories with similarity scores

        Example:
            >>> memory.search("programming languages", user_id="u1")
            [{'content': {'key': 'user_input', 'value': 'I love Python'}, 'similarity': 0.87}]
        """
        session_id = f"user_{user_id}"
        return self._store.search_memories(session_id, query, limit)

    def get_context(
        self,
        query: str,
        user_id: str = "default",
    ) -> str:
        """
        Get rich context string for LLM injection. Combines:
        - Semantic memory matches
        - Knowledge Graph traversal (GraphRAG)

        This is the method you inject into your LLM's system prompt.

        Args:
            query: The user's current query/message
            user_id: User namespace

        Returns:
            Formatted context string ready for LLM injection

        Example:
            >>> context = memory.get_context("What do I do for work?", user_id="u1")
            >>> response = llm.invoke(f"Context: {context}\\n\\nUser: What do I do for work?")
        """
        session_id = f"user_{user_id}"

        # 1. Semantic memory search
        memories = self._store.search_memories(
            session_id, query,
            limit=self._config.max_memory_results
        )

        # 2. Graph context (GraphRAG)
        graph_context = self._graph.get_context(session_id, query)

        # 3. Format for LLM injection
        sections = []

        if memories:
            memory_lines = []
            for m in memories:
                content = m.get('content', {})
                if isinstance(content, dict):
                    val = content.get('value', str(content))
                else:
                    val = str(content)
                score = m.get('similarity', 0)
                memory_lines.append(f"- {val} (relevance: {score:.2f})")
            sections.append("MEMORIES:\n" + "\n".join(memory_lines))

        if graph_context:
            sections.append("KNOWLEDGE GRAPH:\n" + graph_context)

        if not sections:
            return "No memories found for this user yet."

        return "\n\n".join(sections)

    # -------------------------------------------------------------------------
    # Graph-specific API
    # -------------------------------------------------------------------------

    def get_graph(self, user_id: str = "default") -> Dict[str, Any]:
        """
        Get the full Knowledge Graph for a user.

        Returns:
            Dict with 'nodes' and 'edges' lists for visualization.

        Example:
            >>> graph = memory.get_graph(user_id="u1")
            >>> print(f"{len(graph['nodes'])} nodes, {len(graph['edges'])} edges")
        """
        session_id = f"user_{user_id}"
        nodes, edges = self._graph.get_visual_graph(session_id)
        return {"nodes": nodes, "edges": edges}

    def get_stats(self, user_id: str = "default") -> Dict[str, int]:
        """
        Get statistics about a user's memory graph.

        Returns:
            Dict with 'nodes' and 'edges' counts.
        """
        session_id = f"user_{user_id}"
        n, e = self._graph.get_stats(session_id)
        return {"nodes": n, "edges": e}

    def consolidate(self, user_id: str = "default", limit: int = 15) -> str:
        """
        Run the Synaptic Pruning cycle — merges duplicate/redundant nodes in the graph.

        Args:
            user_id: User namespace
            limit: Number of nodes to review (default: 15)

        Returns:
            Summary string of what was done
        """
        session_id = f"user_{user_id}"
        return self._graph.sleep_cycle_pruning(session_id, limit)

    # -------------------------------------------------------------------------
    # Memory Management
    # -------------------------------------------------------------------------

    def delete_user(self, user_id: str) -> Dict[str, int]:
        """
        Delete ALL memories for a user. Irreversible.

        Args:
            user_id: User namespace to delete

        Returns:
            Dict with counts of deleted items
        """
        session_id = f"user_{user_id}"
        return self._store.delete_all(session_id)

    def get_all_memories(self, user_id: str = "default", limit: int = 100) -> List[Dict]:
        """
        Get all stored memories for a user (no search, just list).

        Args:
            user_id: User namespace
            limit: Maximum number to return

        Returns:
            List of memory dicts
        """
        session_id = f"user_{user_id}"
        return self._store.get_all(session_id, limit)
