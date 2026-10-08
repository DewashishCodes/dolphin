"""
Graph Engine (SDK)
===================
Knowledge Graph management: node upsert, edge creation, GraphRAG traversal, and pruning.
Extracted and cleaned from the main Dolphin server for standalone SDK use.
"""

import json
import logging
from typing import Optional, List, Tuple, Dict, Any

from dolphin_memory.config import DolphinConfig
from dolphin_memory.extraction import TripleExtractor

logger = logging.getLogger("dolphin.graph")


class GraphEngine:
    """Manages the Knowledge Graph for Dolphin's persistent memory."""

    def __init__(self, store, config: DolphinConfig):
        """
        Args:
            store: MemoryStore instance (provides the storage backend + embeddings)
            config: DolphinConfig instance
        """
        self._store = store
        self._config = config
        self._extractor = TripleExtractor(config)

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def extract_and_sync(self, session_id: str, text: str) -> List[Dict[str, str]]:
        """
        Extract triples from text and sync them to the Knowledge Graph.

        Returns:
            List of extracted triples as dicts.
        """
        try:
            triples = self._extractor.extract(text)
            if not triples:
                return []

            # Ensure 'User' root node exists
            self._upsert_node(session_id, "User", "Person")

            results = []
            for triple in triples:
                s = triple["s"]
                p = triple["p"]
                o = triple["o"]
                ol = triple.get("ol", "Entity")

                s_id = self._upsert_node(session_id, s, "Person" if s == "User" else "Entity")
                o_id = self._upsert_node(session_id, o, ol)

                if s_id and o_id:
                    self._upsert_edge(session_id, s_id, o_id, p)
                    results.append({"s": s, "p": p, "o": o})
                    logger.info(f"  + Triple Saved: ({s}) -[{p}]-> ({o})")

            if results:
                logger.info(f"✅ Background Graph Sync Complete: {len(results)} facts added.")
            else:
                logger.info("ℹ️ Extraction complete, but no new facts were found.")
                
            return results
        except Exception as e:
            logger.error(f"❌ Background Graph Sync Error: {e}", exc_info=True)
            return []

    def get_context(self, session_id: str, query: str) -> str:
        """
        Build rich context from the Knowledge Graph for a query.
        Combines: User connections + Semantic node matches + Neighborhood traversal.
        """
        try:
            backend = self._store.backend
            context_strings = []

            # 1. User's direct connections
            u_id = backend.get_node_id(session_id, "User")
            if u_id:
                for e in backend.edges_from([u_id], 20):
                    context_strings.append(
                        f"User {e['relationship']} {e['target_name']} ({e['target_label']})"
                    )

            # 2. Semantic node search
            query_vec = self._store.embed(query)
            semantic_nodes = backend.match_nodes(
                session_id, query_vec,
                limit=self._config.max_graph_context,
                threshold=self._config.similarity_threshold + 0.05,
            )

            # 3. Neighborhood traversal (GraphRAG)
            node_ids = []
            for node in semantic_nodes:
                nid = node.get("id")
                if nid:
                    node_ids.append(nid)
                context_strings.append(
                    f"Relevant: {node.get('name', '?')} ({node.get('label', '?')})"
                )

            if node_ids:
                neighbors = self._traverse_neighbors(node_ids)
                context_strings.extend(neighbors)

            # 4. Fallback for small graphs
            if len(context_strings) < 3:
                for r in backend.list_nodes(session_id, 10):
                    context_strings.append(f"Known: {r['name']} is a {r['label']}")

            return "\n".join(sorted(set(context_strings)))
        except Exception as e:
            logger.error(f"Graph context error: {e}", exc_info=True)
            return ""

    def get_visual_graph(self, session_id: str) -> Tuple[List, List]:
        """Get nodes and edges for visualization."""
        try:
            backend = self._store.backend
            return backend.list_nodes(session_id, 500), backend.list_edges(session_id, 1000)
        except Exception as e:
            logger.error(f"Visual graph error: {e}")
            return [], []

    def get_stats(self, session_id: str) -> Tuple[int, int]:
        """Get node/edge counts for a session."""
        try:
            return self._store.backend.stats(session_id)
        except Exception as e:
            logger.error(f"Stats error: {e}")
            return 0, 0

    def sleep_cycle_pruning(self, session_id: str, limit: int = 15) -> str:
        """Consolidate the graph by merging duplicate nodes using local LLM."""
        try:
            backend = self._store.backend

            nodes = backend.list_nodes(
                session_id, limit, exclude_name="User", oldest_first=True
            )

            if len(nodes) < 2:
                return "Not enough nodes to consolidate."

            node_list = "\n".join([f"{n['id']} | {n['name']} ({n['label']})" for n in nodes])
            prompt = (
                "You are a Synaptic Pruning Engine. Find duplicate or redundant nodes.\n\n"
                'Return ONLY a JSON list: [{"keep_id": "uuid", "delete_ids": ["uuid"], "new_name": "Name"}]\n'
                "If no duplicates, return []\n\n"
                f"Nodes:\n{node_list}"
            )

            # Use local LLM for pruning (saves tokens)
            try:
                import ollama
                res = ollama.chat(
                    model=self._config.ollama_model,
                    messages=[{"role": "user", "content": prompt}],
                    format="json",
                )
                raw = res["message"]["content"]
                instructions = self._extractor._parse(raw) or json.loads(raw)
            except Exception as e:
                logger.warning(f"Pruning LLM call failed: {e}")
                return f"Pruning error: {e}"

            if isinstance(instructions, dict):
                instructions = instructions.get("merges", [instructions])

            merge_count = 0
            for instr in instructions:
                if not isinstance(instr, dict):
                    continue
                keep_id = instr.get("keep_id")
                delete_ids = instr.get("delete_ids", [])
                new_name = instr.get("new_name")

                if not keep_id or not delete_ids:
                    continue

                keep_id = str(keep_id).strip()
                delete_ids = [str(d).strip() for d in delete_ids]

                if new_name:
                    try:
                        backend.rename_node(keep_id, new_name)
                    except Exception:
                        pass

                for d_id in delete_ids:
                    try:
                        backend.merge_node(keep_id, d_id)
                        merge_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to merge node {d_id}: {e}")

            return f"Merged {merge_count} redundant nodes."
        except Exception as e:
            logger.error(f"Pruning error: {e}", exc_info=True)
            return f"Pruning error: {e}"

    # -------------------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------------------

    def _upsert_node(self, session_id: str, name: str, label: str) -> Optional[str]:
        """Insert or retrieve a graph node. Returns UUID or None."""
        try:
            backend = self._store.backend

            node_id = backend.get_node_id(session_id, name)
            if node_id:
                return node_id

            vec = self._store.embed(f"{label}: {name}")
            return backend.insert_node(session_id, name, label, vec)
        except Exception as e:
            logger.error(f"Node upsert failed for '{name}': {e}")
            return None

    def _upsert_edge(self, session_id: str, s_id: str, o_id: str, rel: str):
        """Insert or reinforce a graph edge."""
        if not s_id or not o_id:
            return
        try:
            self._store.backend.upsert_edge(session_id, s_id, o_id, rel)
        except Exception as e:
            logger.error(f"Edge upsert failed for {rel}: {e}")

    def _traverse_neighbors(self, node_ids: List[str]) -> List[str]:
        """Fetch 1-hop neighborhood for given nodes (GraphRAG)."""
        if not node_ids:
            return []
        results = []
        try:
            backend = self._store.backend

            # One format for both directions: an edge between two matched nodes
            # comes back from both queries and must collapse to a single line.
            for e in backend.edges_from(node_ids, 15) + backend.edges_to(node_ids, 15):
                line = (
                    f"{e['source_name']} {e['relationship']} "
                    f"{e['target_name']} ({e['target_label']})"
                )
                if line not in results:
                    results.append(line)
        except Exception as e:
            logger.error(f"Traversal error: {e}")

        return results
