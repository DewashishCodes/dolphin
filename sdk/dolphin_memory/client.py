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
import threading
import concurrent.futures
from datetime import datetime, timezone
import dateutil.parser
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

        # Threading for background extraction
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self._lock = threading.RLock()

        logger.info("🐬 Dolphin Memory initialized (Polished)")

    def _get_relative_time(self, timestr: Optional[str]) -> str:
        """Convert an ISO timestamp to a human-readable relative time."""
        if not timestr:
            return "Recently"
        try:
            past = dateutil.parser.isoparse(timestr)
            diff = datetime.now(timezone.utc) - past
            m = int(diff.total_seconds() // 60)
            if m < 1:
                return "Just now"
            if m < 60:
                return f"{m}m ago"
            h = m // 60
            if h < 24:
                return f"{h}h ago"
            d = h // 24
            return f"{d}d ago"
        except Exception:
            return "Recently"

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
        1. Store/Reinforce the raw text (with semantic deduplication)
        2. Extract entities & relationships in the background
        """
        session_id = f"user_{user_id}"

        # 1. Semantic Deduplication Check
        if self._config.deduplicate:
            existing = self._store.search_memories(
                session_id, text, limit=1, threshold=self._config.dedupe_threshold
            )
            if existing:
                match = existing[0]
                memory_id = match.get('id')
                logger.info(f"Dedupe: Reinforcing existing memory {memory_id} (Similarity: {match.get('similarity'):.2f})")
                self._store.update_memory_access(memory_id)
                
                # Still trigger extraction in background just in case new text has more info
                if self._config.auto_extract:
                    self._run_bg_extraction(session_id, text)
                    
                return {
                    "memory_id": memory_id,
                    "status": "reinforced",
                    "similarity": match.get('similarity')
                }

        # 2. Store as a new structured memory
        memory_data = {"key": "user_input", "value": text}
        if metadata:
            memory_data.update(metadata)

        memory_id = self._store.add_memory(
            session_id=session_id,
            memory_type="conversation",
            content=memory_data,
            confidence=1.0,
        )

        # 3. Background extraction (NON-BLOCKING)
        if self._config.auto_extract:
            if self._config.enable_background_extraction:
                self._run_bg_extraction(session_id, text)
            else:
                self._graph.extract_and_sync(session_id, text)

        return {
            "memory_id": memory_id,
            "status": "created",
            "triples_pending": self._config.enable_background_extraction
        }

    def _run_bg_extraction(self, session_id: str, text: str):
        """Schedule graph extraction in the background thread pool."""
        logger.debug(f"Scheduling background extraction for {session_id}")
        self._executor.submit(self._graph.extract_and_sync, session_id, text)

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
                val = content.get('value', str(content)) if isinstance(content, dict) else str(content)
                rel_time = self._get_relative_time(m.get('created_at'))
                memory_lines.append(f"- [{rel_time}]: {val}")
            sections.append("### RELEVANT MEMORIES\n" + "\n".join(memory_lines))

        if graph_context:
            sections.append("### KNOWLEDGE GRAPH\n" + graph_context)

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
