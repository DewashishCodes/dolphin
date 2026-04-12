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
            store: MemoryStore instance (provides Supabase client + embeddings)
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

                s_label = "Person" if s == "User" else "Entity"
                s_id = self._upsert_node(session_id, s, s_label)
                o_id = self._upsert_node(session_id, o, ol)

                if s_id and o_id:
                    self._upsert_edge(session_id, s_id, o_id, p)
                    results.append({"s": s, "p": p, "o": o})

            logger.info(f"Synced {len(results)} triples to graph")
            return results
        except Exception as e:
            logger.error(f"Graph sync error: {e}", exc_info=True)
            return []

    def get_context(self, session_id: str, query: str) -> str:
        """
        Build rich context from the Knowledge Graph for a query.
        Combines: User connections + Semantic node matches + Neighborhood traversal.
        """
        try:
            supabase = self._store.supabase
            context_strings = []

            # 1. User's direct connections
            u_node = supabase.table("graph_nodes") \
                .select("id").eq("session_id", session_id).eq("name", "User").execute()

            if u_node.data:
                u_id = u_node.data[0]["id"]
                edges = supabase.table("graph_edges").select(
                    "relationship, target:graph_nodes!graph_edges_target_id_fkey(name, label)"
                ).eq("source_id", u_id).limit(20).execute()

                for e in edges.data:
                    target = e.get("target", {})
                    context_strings.append(
                        f"User {e['relationship']} {target.get('name', '?')} ({target.get('label', '?')})"
                    )

            # 2. Semantic node search
            query_vec = self._store.embed(query)
            semantic_nodes = supabase.rpc("match_graph_nodes", {
                "query_embedding": query_vec,
                "match_threshold": self._config.similarity_threshold + 0.05,
                "match_count": self._config.max_graph_context,
                "p_session_id": session_id,
            }).execute()

            # 3. Neighborhood traversal (GraphRAG)
            node_ids = []
            if semantic_nodes.data:
                for node in semantic_nodes.data:
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
                recent = supabase.table("graph_nodes") \
                    .select("name, label").eq("session_id", session_id).limit(10).execute()
                for r in recent.data:
                    context_strings.append(f"Known: {r['name']} is a {r['label']}")

            return "\n".join(sorted(set(context_strings)))
        except Exception as e:
            logger.error(f"Graph context error: {e}", exc_info=True)
            return ""

    def get_visual_graph(self, session_id: str) -> Tuple[List, List]:
        """Get nodes and edges for visualization."""
        try:
            supabase = self._store.supabase
            nodes = supabase.table("graph_nodes") \
                .select("id, name, label").eq("session_id", session_id).limit(500).execute()
            edges = supabase.table("graph_edges") \
                .select("source_id, target_id, relationship").eq("session_id", session_id).limit(1000).execute()
            return nodes.data or [], edges.data or []
        except Exception as e:
            logger.error(f"Visual graph error: {e}")
            return [], []

    def get_stats(self, session_id: str) -> Tuple[int, int]:
        """Get node/edge counts for a session."""
        try:
            supabase = self._store.supabase
            n = supabase.table("graph_nodes") \
                .select("id", count="exact").eq("session_id", session_id).execute()
            e = supabase.table("graph_edges") \
                .select("id", count="exact").eq("session_id", session_id).execute()
            return n.count or 0, e.count or 0
        except Exception as e:
            logger.error(f"Stats error: {e}")
            return 0, 0

    def sleep_cycle_pruning(self, session_id: str, limit: int = 15) -> str:
        """Consolidate the graph by merging duplicate nodes using local LLM."""
        try:
            supabase = self._store.supabase

            nodes = supabase.table("graph_nodes") \
                .select("id, name, label").eq("session_id", session_id) \
                .neq("name", "User").order("created_at").limit(limit).execute().data

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
                        supabase.table("graph_nodes") \
                            .update({"name": new_name}).eq("id", keep_id).execute()
                    except Exception:
                        pass

                for d_id in delete_ids:
                    try:
                        supabase.table("graph_edges") \
                            .update({"source_id": keep_id}).eq("source_id", d_id).execute()
                        supabase.table("graph_edges") \
                            .update({"target_id": keep_id}).eq("target_id", d_id).execute()
                        supabase.table("graph_nodes") \
                            .delete().eq("id", d_id).execute()
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
            supabase = self._store.supabase

            res = supabase.table("graph_nodes") \
                .select("id").eq("session_id", session_id).eq("name", name).execute()

            if res.data:
                return res.data[0]["id"]

            vec = self._store.embed(f"{label}: {name}")
            new = supabase.table("graph_nodes").insert({
                "session_id": session_id,
                "name": name,
                "label": label,
                "embedding": vec,
            }).execute()

            return new.data[0]["id"] if new.data else None
        except Exception as e:
            logger.error(f"Node upsert failed for '{name}': {e}")
            return None

    def _upsert_edge(self, session_id: str, s_id: str, o_id: str, rel: str):
        """Insert or reinforce a graph edge (deduplication via check-then-insert)."""
        if not s_id or not o_id:
            return
        try:
            supabase = self._store.supabase

            existing = supabase.table("graph_edges") \
                .select("id, access_count") \
                .eq("source_id", s_id).eq("target_id", o_id).eq("relationship", rel) \
                .execute()

            if existing.data:
                edge = existing.data[0]
                count = edge.get("access_count", 1)
                supabase.table("graph_edges").update({
                    "access_count": count + 1,
                    "weight": min(1.0 + count * 0.1, 5.0),
                }).eq("id", edge["id"]).execute()
            else:
                supabase.table("graph_edges").insert({
                    "session_id": session_id,
                    "source_id": s_id,
                    "target_id": o_id,
                    "relationship": rel,
                }).execute()
        except Exception as e:
            logger.error(f"Edge upsert failed for {rel}: {e}")

    def _traverse_neighbors(self, node_ids: List[str]) -> List[str]:
        """Fetch 1-hop neighborhood for given nodes (GraphRAG)."""
        if not node_ids:
            return []
        results = []
        try:
            supabase = self._store.supabase

            out = supabase.table("graph_edges").select(
                "relationship, source:graph_nodes!graph_edges_source_id_fkey(name), "
                "target:graph_nodes!graph_edges_target_id_fkey(name, label)"
            ).in_("source_id", node_ids).limit(15).execute()

            for e in out.data:
                s = e.get("source", {}).get("name", "?")
                t = e.get("target", {}).get("name", "?")
                tl = e.get("target", {}).get("label", "?")
                results.append(f"{s} {e['relationship']} {t} ({tl})")

            inc = supabase.table("graph_edges").select(
                "relationship, source:graph_nodes!graph_edges_source_id_fkey(name, label), "
                "target:graph_nodes!graph_edges_target_id_fkey(name)"
            ).in_("target_id", node_ids).limit(15).execute()

            for e in inc.data:
                s = e.get("source", {}).get("name", "?")
                sl = e.get("source", {}).get("label", "?")
                t = e.get("target", {}).get("name", "?")
                results.append(f"{s} ({sl}) {e['relationship']} {t}")
        except Exception as e:
            logger.error(f"Traversal error: {e}")

        return results
