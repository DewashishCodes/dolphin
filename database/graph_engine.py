"""
Dolphin V2 Graph Engine
========================
Manages the Knowledge Graph: entity extraction, storage, traversal, and pruning.

V2 Changes:
- Cloud LLM extraction (Gemini) with Ollama fallback
- Edge deduplication (upsert instead of blind insert)
- Proper error handling with structured logging
- Memory lifecycle: access tracking, confidence scoring
- Async-ready extraction method
"""

import json
import re
import logging
from database.connection import db

logger = logging.getLogger("dolphin.graph")


class GraphEngine:
    """Core Knowledge Graph engine for Dolphin's persistent memory."""

    def _sanitize_and_parse(self, raw_text: str) -> list:
        """Force-cleans LLM output into a valid Python list of triples."""
        try:
            # 1. Strip everything except the JSON array
            match = re.search(r'\[.*\]', raw_text, re.DOTALL)
            clean_text = match.group(0) if match else raw_text

            # 2. Fix common LLM hallucinations with quotes
            clean_text = clean_text.replace('""', '"').replace('\\"', '"')

            # 3. Parse JSON
            data = json.loads(clean_text)

            # Ensure it's a list
            if isinstance(data, dict):
                data = [data]
            return data
        except (json.JSONDecodeError, AttributeError) as e:
            logger.warning(f"JSON parse failed: {e}. Raw (first 200 chars): {raw_text[:200]}")
            return []

    def _extract_triples_cloud(self, text: str) -> list:
        """Extract triples using cloud LLM (Gemini). Primary extraction method."""
        try:
            llm = db.get_llm({'provider': 'gemini'})
            prompt = (
                "You are a Knowledge Graph extraction engine. "
                "Extract factual relationships from the user's message.\n\n"
                'Return ONLY a valid JSON array. Format: [{"s": "Subject", "p": "RELATIONSHIP", "o": "Object", "ol": "Label"}]\n'
                'Example: [{"s": "User", "p": "LIVES_IN", "o": "Pune", "ol": "City"}]\n\n'
                "Rules:\n"
                "- Use 'User' as the subject when the speaker is talking about themselves\n"
                "- Relationship names should be UPPER_SNAKE_CASE\n"
                "- Labels should be: Person, City, Country, Skill, Language, Company, Role, Concept, Event, or Entity\n"
                "- Only extract concrete, factual information. Skip greetings, filler, and opinions.\n"
                "- If no facts found, return []\n\n"
                f"User message: \"{text}\""
            )
            res = llm.invoke(prompt)
            content = res.content if hasattr(res, 'content') else str(res)

            # Handle Gemini response wrapping
            if isinstance(content, list) and len(content) > 0:
                if isinstance(content[0], dict) and 'text' in content[0]:
                    content = content[0]['text']
                else:
                    content = str(content[0])

            return self._sanitize_and_parse(content)
        except Exception as e:
            logger.warning(f"Cloud extraction failed: {e}")
            return []

    def _extract_triples_local(self, text: str) -> list:
        """Extract triples using local Ollama (Llama 3.2). Fallback method."""
        try:
            import ollama
            response = ollama.chat(
                model='llama3.2',
                messages=[{
                    'role': 'system',
                    'content': 'You are a Knowledge Graph engine. Return ONLY a JSON list. Format: [{"s": "User", "p": "LIVES_IN", "o": "Pune"}]'
                }, {
                    'role': 'user',
                    'content': f"Extract facts from: '{text}'"
                }],
                format='json',
                options={'temperature': 0}
            )
            raw_res = response['message']['content']
            return self._sanitize_and_parse(raw_res)
        except ImportError:
            logger.error("Ollama not installed. Install with: pip install ollama")
            return []
        except Exception as e:
            logger.warning(f"Local extraction failed (is Ollama running?): {e}")
            return []

    def extract_and_sync_graph(self, session_id: str, text: str, source_node_id=None, use_cloud: bool = False):
        """
        Extract triples from text and sync to the Knowledge Graph.

        Args:
            session_id: Namespace/user scope for the graph
            text: Raw text to extract facts from
            source_node_id: Optional source node to link extracted facts to
            use_cloud: If True, use cloud LLM (Gemini) instead of local Ollama

        Returns:
            List of extracted triples as dicts, or empty list on failure
        """
        try:
            # LOCAL-FIRST: Use Ollama (saves tokens, works offline)
            # Cloud is optional fallback only when explicitly requested or Ollama fails
            if use_cloud:
                triples = self._extract_triples_cloud(text)
                if not triples:
                    logger.info("Cloud extraction returned empty, trying local fallback...")
                    triples = self._extract_triples_local(text)
            else:
                triples = self._extract_triples_local(text)
                if not triples:
                    logger.info("Local extraction returned empty, trying cloud fallback...")
                    triples = self._extract_triples_cloud(text)

            if not triples:
                logger.info(f"No triples extracted from: {text[:100]}")
                return []

            # Ensure 'User' node exists if we are in normal chat mode
            if not source_node_id:
                self._upsert_node(session_id, "User", "Person")

            results = []
            for item in triples:
                # Validate item is a dict
                if not isinstance(item, dict):
                    logger.debug(f"Skipping non-dict item: {type(item)}: {item}")
                    continue

                # Handle various key names the LLM might use
                s = item.get('s') or item.get('subject') or "User"
                p = item.get('p') or item.get('predicate') or "RELATED_TO"
                o = item.get('o') or item.get('object')
                ol = item.get('ol') or item.get('label') or "Entity"

                if not o:
                    continue

                # Determine subject label
                s_label = "Person" if str(s) == "User" else "Entity"

                # Sync to Supabase
                s_id = self._upsert_node(session_id, str(s), s_label)
                o_id = self._upsert_node(session_id, str(o), str(ol))

                if not s_id or not o_id:
                    logger.warning(f"Failed to upsert nodes: s={s} (id={s_id}), o={o} (id={o_id})")
                    continue

                self._upsert_edge(session_id, s_id, o_id, str(p).upper())

                # Link to source document if applicable
                if source_node_id:
                    self._upsert_edge(session_id, source_node_id, s_id, "MENTIONS")

                results.append({"s": s, "p": p, "o": o})

            logger.info(f"Extracted {len(results)} triples from message")
            return results
        except Exception as e:
            logger.error(f"Graph sync error: {e}", exc_info=True)
            return []

    def _upsert_node(self, session_id: str, name: str, label: str):
        """Insert or retrieve a graph node. Returns the node UUID or None."""
        try:
            # Check if node already exists
            res = db.supabase.table("graph_nodes") \
                .select("id") \
                .eq("session_id", session_id) \
                .eq("name", name) \
                .execute()

            if res.data:
                node_id = res.data[0]['id']
                # Update access tracking
                try:
                    db.supabase.table("graph_nodes") \
                        .update({
                            "last_accessed": "now()",
                            "access_count": res.data[0].get('access_count', 0) + 1
                        }) \
                        .eq("id", node_id) \
                        .execute()
                except Exception:
                    pass  # Non-critical: access tracking may fail on older schemas
                return node_id

            # Create new node with embedding
            vec = db.embeddings.embed_query(f"{label}: {name}")
            new_node = db.supabase.table("graph_nodes").insert({
                "session_id": session_id,
                "name": name,
                "label": label,
                "embedding": vec
            }).execute()

            if new_node.data:
                return new_node.data[0]['id']
            else:
                logger.error(f"Node insert returned no data: name={name}")
                return None
        except Exception as e:
            logger.error(f"Failed to upsert node '{name}': {e}")
            return None

    def _upsert_edge(self, session_id: str, s_id: str, o_id: str, rel: str):
        """
        Insert or update a graph edge. Uses upsert to prevent duplicates.
        On conflict (same source, target, relationship), increments access count.
        """
        if not s_id or not o_id:
            return

        try:
            # Check if edge exists first (Supabase doesn't support ON CONFLICT via API easily)
            existing = db.supabase.table("graph_edges") \
                .select("id, access_count") \
                .eq("source_id", s_id) \
                .eq("target_id", o_id) \
                .eq("relationship", rel) \
                .execute()

            if existing.data:
                # Edge exists — update access count and timestamp
                edge_id = existing.data[0]['id']
                current_count = existing.data[0].get('access_count', 1)
                db.supabase.table("graph_edges") \
                    .update({
                        "last_accessed": "now()",
                        "access_count": current_count + 1,
                        "weight": min(1.0 + (current_count * 0.1), 5.0)  # Weight grows with reinforcement, cap at 5
                    }) \
                    .eq("id", edge_id) \
                    .execute()
                logger.debug(f"Reinforced edge: {rel} (count: {current_count + 1})")
            else:
                # New edge — insert
                db.supabase.table("graph_edges").insert({
                    "session_id": session_id,
                    "source_id": s_id,
                    "target_id": o_id,
                    "relationship": rel
                }).execute()
                logger.debug(f"Created edge: {s_id} -{rel}-> {o_id}")
        except Exception as e:
            logger.error(f"Failed to upsert edge {rel}: {e}")

    def _traverse_neighbors(self, node_ids: list) -> list:
        """GraphRAG: Fetches 1-hop neighborhood for a list of nodes."""
        if not node_ids:
            return []

        results = []
        try:
            # 1. Outgoing: Selected Nodes -> Targets
            out_edges = db.supabase.table("graph_edges").select(
                "relationship, source:graph_nodes!graph_edges_source_id_fkey(name), target:graph_nodes!graph_edges_target_id_fkey(name, label)"
            ).in_("source_id", node_ids).limit(15).execute()

            for e in out_edges.data:
                s_name = e.get('source', {}).get('name', '?')
                t_name = e.get('target', {}).get('name', '?')
                t_label = e.get('target', {}).get('label', '?')
                results.append(f"Fact: {s_name} {e['relationship']} {t_name} ({t_label})")

            # 2. Incoming: Sources -> Selected Nodes
            in_edges = db.supabase.table("graph_edges").select(
                "relationship, source:graph_nodes!graph_edges_source_id_fkey(name, label), target:graph_nodes!graph_edges_target_id_fkey(name)"
            ).in_("target_id", node_ids).limit(15).execute()

            for e in in_edges.data:
                s_name = e.get('source', {}).get('name', '?')
                s_label = e.get('source', {}).get('label', '?')
                t_name = e.get('target', {}).get('name', '?')
                results.append(f"Fact: {s_name} ({s_label}) {e['relationship']} {t_name}")

        except Exception as e:
            logger.error(f"Traversal error: {e}", exc_info=True)

        return results

    def get_graph_context(self, session_id: str, query: str) -> str:
        """
        Build hybrid context from the Knowledge Graph for a given query.
        Combines: User connections + Semantic node search + Neighborhood traversal.
        """
        try:
            context_strings = []

            # 1. Find the User's direct connections
            u_node = db.supabase.table("graph_nodes") \
                .select("id") \
                .eq("session_id", session_id) \
                .eq("name", "User") \
                .execute()

            if u_node.data:
                u_id = u_node.data[0]['id']
                edges = db.supabase.table("graph_edges").select(
                    "relationship, target:graph_nodes!graph_edges_target_id_fkey(name, label)"
                ).eq("source_id", u_id).limit(20).execute()

                for e in edges.data:
                    target = e.get('target', {})
                    context_strings.append(
                        f"User {e['relationship']} {target.get('name', '?')} ({target.get('label', '?')})"
                    )

            # 2. Semantic node search (find relevant nodes by embedding similarity)
            query_vec = db.embeddings.embed_query(query)
            semantic_nodes = db.supabase.rpc('match_graph_nodes', {
                'query_embedding': query_vec,
                'match_threshold': 0.3,
                'match_count': 15,
                'p_session_id': session_id
            }).execute()

            # 3. GraphRAG: Neighborhood traversal from semantically matched nodes
            relevant_node_ids = []
            if semantic_nodes.data:
                for node in semantic_nodes.data:
                    node_id = node.get('id')
                    if node_id:
                        relevant_node_ids.append(node_id)
                    context_strings.append(
                        f"Relevant Topic: {node.get('name', 'Unknown')} ({node.get('label', 'Entity')})"
                    )

            neighborhood_facts = self._traverse_neighbors(relevant_node_ids)
            context_strings.extend(neighborhood_facts)

            # 4. Fallback: if graph is small, grab recent nodes
            if len(context_strings) < 3:
                recent = db.supabase.table("graph_nodes") \
                    .select("name, label") \
                    .eq("session_id", session_id) \
                    .limit(10) \
                    .execute()
                for r in recent.data:
                    context_strings.append(f"Known Fact: {r['name']} is a {r['label']}")

            # Deduplicate and return
            return "\n".join(list(set(context_strings)))
        except Exception as e:
            logger.error(f"Graph context retrieval error: {e}", exc_info=True)
            return ""

    def get_visual_graph(self, session_id=None):
        """Fetches nodes and edges for 3D visualization."""
        try:
            if session_id:
                nodes_data = db.supabase.table("graph_nodes") \
                    .select("id, name, label") \
                    .eq("session_id", session_id) \
                    .limit(200).execute()
                edges_data = db.supabase.table("graph_edges") \
                    .select("source_id, target_id, relationship") \
                    .limit(300).execute()
                return nodes_data.data, edges_data.data

            # Global graph (all sessions)
            nodes_data = db.supabase.table("graph_nodes") \
                .select("id, name, label") \
                .limit(1000).execute()
            edges_data = db.supabase.table("graph_edges") \
                .select("source_id, target_id, relationship") \
                .limit(2000).execute()

            return nodes_data.data, edges_data.data
        except Exception as e:
            logger.error(f"Visual graph error: {e}")
            return [], []

    def get_stats(self, session_id=None):
        """Returns the current size of the knowledge graph."""
        try:
            if session_id:
                nodes = db.supabase.table("graph_nodes") \
                    .select("id", count="exact") \
                    .eq("session_id", session_id).execute()
                edges = db.supabase.table("graph_edges") \
                    .select("id", count="exact") \
                    .eq("session_id", session_id).execute()
                return nodes.count, edges.count

            nodes = db.supabase.table("graph_nodes") \
                .select("id", count="exact").execute()
            edges = db.supabase.table("graph_edges") \
                .select("id", count="exact").execute()
            return nodes.count, edges.count
        except Exception as e:
            logger.error(f"Stats error: {e}")
            return 0, 0

    def _relink_edges(self, old_node_id: str, new_node_id: str):
        """Moves all relationships from an old node to a new master node."""
        try:
            db.supabase.table("graph_edges") \
                .update({"source_id": new_node_id}) \
                .eq("source_id", old_node_id).execute()
            db.supabase.table("graph_edges") \
                .update({"target_id": new_node_id}) \
                .eq("target_id", old_node_id).execute()
        except Exception as e:
            logger.error(f"Edge relink error ({old_node_id} -> {new_node_id}): {e}")

    def sleep_cycle_pruning(self, session_id: str, limit: int):
        """
        Uses LLM to consolidate the graph by merging duplicate/redundant nodes.
        Tries cloud LLM first, falls back to local Ollama.
        """
        try:
            # 1. Fetch nodes (oldest first, skip the User root node)
            nodes = db.supabase.table("graph_nodes") \
                .select("id, name, label") \
                .eq("session_id", session_id) \
                .neq("name", "User") \
                .order("created_at") \
                .limit(limit).execute().data

            if len(nodes) < 2:
                return "Not enough nodes to consolidate."

            # 2. Ask LLM to find duplicates
            node_list_str = "\n".join([f"{n['id']} | {n['name']} ({n['label']})" for n in nodes])

            pruning_prompt = (
                "You are a Synaptic Pruning Engine. Look at these graph nodes and identify duplicates or redundancies.\n\n"
                'Return ONLY a JSON list. Format: [{"keep_id": "uuid-1", "delete_ids": ["uuid-2", "uuid-3"], "new_name": "Standardized Name"}]\n'
                "If no duplicates found, return []\n\n"
                f"Nodes:\n{node_list_str}"
            )

            # Try cloud LLM first
            instructions = []
            try:
                llm = db.get_llm({'provider': 'gemini'})
                res = llm.invoke(pruning_prompt)
                content = res.content if hasattr(res, 'content') else str(res)
                if isinstance(content, list) and len(content) > 0:
                    if isinstance(content[0], dict) and 'text' in content[0]:
                        content = content[0]['text']
                instructions = self._sanitize_and_parse(content)
            except Exception as e:
                logger.warning(f"Cloud pruning failed, trying local: {e}")

            # Fallback to local
            if not instructions:
                try:
                    import ollama
                    res = ollama.chat(
                        model='llama3.2',
                        messages=[{'role': 'user', 'content': pruning_prompt}],
                        format='json'
                    )
                    raw = res['message']['content']
                    instructions = json.loads(raw)
                except Exception as e:
                    logger.error(f"Local pruning also failed: {e}")
                    return f"Pruning error: could not reach any LLM."

            # Normalize response
            if isinstance(instructions, dict):
                instructions = instructions.get('merges', []) if 'merges' in instructions else [instructions]

            merge_count = 0
            for instr in instructions:
                if not isinstance(instr, dict):
                    continue

                keep_id = instr.get('keep_id')
                delete_ids = instr.get('delete_ids', [])
                new_name = instr.get('new_name')

                if not keep_id or not delete_ids:
                    continue

                # Sanitize IDs (remove hallucinated prefixes)
                keep_id = str(keep_id).replace("ID:", "").replace("id:", "").strip()
                delete_ids = [str(d).replace("ID:", "").replace("id:", "").strip() for d in delete_ids]

                # Update the 'keep' node's name
                if new_name:
                    try:
                        db.supabase.table("graph_nodes") \
                            .update({"name": new_name}) \
                            .eq("id", keep_id).execute()
                    except Exception as e:
                        logger.warning(f"Failed to rename node {keep_id}: {e}")

                # Re-link and delete
                for d_id in delete_ids:
                    try:
                        self._relink_edges(d_id, keep_id)
                        db.supabase.table("graph_nodes") \
                            .delete().eq("id", d_id).execute()
                        merge_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to delete node {d_id}: {e}")

            return f"Success! Merged {merge_count} redundant nodes into master entities."
        except Exception as e:
            logger.error(f"Pruning error: {e}", exc_info=True)
            return f"Pruning Error: {e}"


graph_engine = GraphEngine()