import ollama
import json
import re
from database.connection import db

class GraphEngine:
    def _sanitize_and_parse(self, raw_text):
        """Force-cleans the Llama output into a valid Python list."""
        try:
            # 1. Strip everything except the brackets
            match = re.search(r'\[.*\]', raw_text, re.DOTALL)
            clean_text = match.group(0) if match else raw_text
            
            # 2. Fix the "Double Quote" hallucination: '""s""' -> '"s"'
            # This handles the specific error you were seeing: '"s"'
            clean_text = clean_text.replace('""', '"').replace('\\"', '"')
            
            # 3. Handle key variations manually if json.loads fails
            data = json.loads(clean_text)
            
            # Ensure it's a list
            if isinstance(data, dict):
                data = [data]
            return data
        except Exception as e:
            print(f"JSON Parse Attempt Failed: {e}. Raw: {raw_text[:100]}")
            return []

    def extract_and_sync_graph(self, session_id, text, source_node_id=None):
        try:
            # Using ollama.chat for better instruction following
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
            triples = self._sanitize_and_parse(raw_res)
            
            if not triples: return []

            # Ensure 'User' node exists if we are in normal chat mode (no source node)
            if not source_node_id:
                self._upsert_node(session_id, "User", "Person")

            results = []
            for item in triples:
                # FIX: Ensure item is a dictionary before calling .get()
                if isinstance(item, str):
                    print(f"Skipping malformed item (str): {item}")
                    continue
                    
                # Logic to handle different key names the model might use
                # We check for string keys, escaped keys, and full words
                s = item.get('s') or item.get('subject') or item.get('"s"') or "User"
                p = item.get('p') or item.get('predicate') or item.get('"p"') or "RELATED_TO"
                o = item.get('o') or item.get('object') or item.get('"o"')
                ol = item.get('ol') or item.get('label') or item.get('"ol"') or "Entity"

                if not o: continue

                # Sync to Supabase
                s_id = self._upsert_node(session_id, str(s), "Person" if str(s) == "User" else "Entity")
                o_id = self._upsert_node(session_id, str(o), str(ol))
                self._create_edge(session_id, s_id, o_id, str(p).upper())
                
                # LINK TO SOURCE (If applicable)
                if source_node_id:
                     # Connect the SUBJECT of the fact to the Source File
                     # e.g., File [MENTIONS] Elon Musk
                     self._create_edge(session_id, source_node_id, s_id, "MENTIONS")

                results.append({"s": s, "p": p, "o": o})
            
            return results
        except Exception as e:
            print(f"Graph Sync Error: {e}")
            return []

    def _upsert_node(self, session_id, name, label):
        try:
            res = db.supabase.table("graph_nodes").select("id").eq("session_id", session_id).eq("name", name).execute()
            if res.data: return res.data[0]['id']
            
            vec = db.embeddings.embed_query(f"{label}: {name}")
            new_node = db.supabase.table("graph_nodes").insert({
                "session_id": session_id, "name": name, "label": label, "embedding": vec
            }).execute()
            return new_node.data[0]['id']
        except: return None

    def _create_edge(self, session_id, s_id, o_id, rel):
        if not s_id or not o_id: return
        try:
            db.supabase.table("graph_edges").insert({
                "session_id": session_id, "source_id": s_id, "target_id": o_id, "relationship": rel
            }).execute()
        except: pass

    def _traverse_neighbors(self, node_ids):
        """GraphRAG: Fetches 1-hop neighborhood for a list of nodes."""
        if not node_ids: return []
        results = []
        try:
            # 1. Outgoing: Selected Nodes -> Targets
            out_edges = db.supabase.table("graph_edges").select(
                "relationship, source:graph_nodes!graph_edges_source_id_fkey(name), target:graph_nodes!graph_edges_target_id_fkey(name, label)"
            ).in_("source_id", node_ids).limit(15).execute()
            
            for e in out_edges.data:
                s_name = e['source']['name']
                t_name = e['target']['name']
                t_label = e['target']['label']
                results.append(f"Fact: {s_name} {e['relationship']} {t_name} ({t_label})")

            # 2. Incoming: Sources -> Selected Nodes
            in_edges = db.supabase.table("graph_edges").select(
                "relationship, source:graph_nodes!graph_edges_source_id_fkey(name, label), target:graph_nodes!graph_edges_target_id_fkey(name)"
            ).in_("target_id", node_ids).limit(15).execute()
            
            for e in in_edges.data:
                s_name = e['source']['name']
                s_label = e['source']['label']
                t_name = e['target']['name']
                results.append(f"Fact: {s_name} ({s_label}) {e['relationship']} {t_name}")
                
        except Exception as e:
            print(f"Traversal Error: {e}")
            
        return results

    def get_graph_context(self, session_id, query):
        try:
            # 1. FIND THE USER'S PRIMARY CONNECTIONS
            # We look for 'User' or the session_id as a fallback
            u_node = db.supabase.table("graph_nodes").select("id").eq("session_id", session_id).eq("name", "User").execute()
            
            context_strings = []
            if u_node.data:
                u_id = u_node.data[0]['id']
                edges = db.supabase.table("graph_edges").select(
                    "relationship, target:graph_nodes!graph_edges_target_id_fkey(name, label)"
                ).eq("source_id", u_id).limit(20).execute()
                
                for e in edges.data:
                    target = e['graph_nodes']
                    context_strings.append(f"User {e['relationship']} {target['name']} ({target['label']})")

            # 2. SEMANTIC NODE SEARCH (The Revolutionary Part)
            # Find nodes that match the query even if they aren't connected to the 'User' yet
            query_vec = db.embeddings.embed_query(query)
            semantic_nodes = db.supabase.rpc('match_graph_nodes', {
                'query_embedding': query_vec,
                'match_threshold': 0.3,
                'match_count': 15,
                'p_session_id': session_id
            }).execute()

            # 3. GraphRAG: NEIGHBORHOOD TRAVERSAL
            # Extract IDs of relevant nodes and fetch their neighbors
            relevant_node_ids = [n['id'] for n in semantic_nodes.data]
            neighborhood_facts = self._traverse_neighbors(relevant_node_ids)
            
            # Combine Context: User Links + Semantic Matches + Neighborhood Facts
            for node in semantic_nodes.data:
                context_strings.append(f"Relevant Topic: {node['name']} ({node['label']})")
            
            context_strings.extend(neighborhood_facts)

            # 4. GLOBAL FALLBACK: If the graph is small, just grab the last 10 nodes
            if len(context_strings) < 3:
                recent = db.supabase.table("graph_nodes").select("name, label").eq("session_id", session_id).limit(10).execute()
                for r in recent.data:
                    context_strings.append(f"Known Fact: {r['name']} is a {r['label']}")

            return "\n".join(list(set(context_strings))) # Deduplicate
        except Exception as e:
            print(f"Graph Retrieval Error: {e}")
            return ""
        
    def get_stats(self, session_id):
        """Returns the current size of the user's brain."""
        try:
            nodes = db.supabase.table("graph_nodes").select("id", count="exact").eq("session_id", session_id).execute()
            edges = db.supabase.table("graph_edges").select("id", count="exact").eq("session_id", session_id).execute()
            return nodes.count, edges.count
        except:
            return 0, 0
        
    def _relink_edges(self, old_node_id, new_node_id):
        """Moves all relationships from an old node to a new master node."""
        # Update source nodes
        db.supabase.table("graph_edges").update({"source_id": new_node_id}).eq("source_id", old_node_id).execute()
        # Update target nodes
        db.supabase.table("graph_edges").update({"target_id": new_node_id}).eq("target_id", old_node_id).execute()

    def sleep_cycle_pruning(self, session_id, limit):
        """Uses Local Llama to consolidate the graph."""
        try:
            # 1. Fetch 'limit' number of nodes (oldest first)
            nodes = db.supabase.table("graph_nodes")\
                .select("id, name, label")\
                .eq("session_id", session_id)\
                .neq("name", "User")\
                .order("created_at")\
                .limit(limit).execute().data
            
            if len(nodes) < 2: return "Not enough nodes to consolidate."

            # 2. Ask Llama to find duplicates or redundant info
            node_list_str = "\n".join([f"ID:{n['id']} | {n['name']} ({n['label']})" for n in nodes])
            
            pruning_prompt = f"""
            System: You are a Synaptic Pruning Engine. Look at these nodes and identify duplicates or redundancies.
            
            Return ONLY a JSON list of merges. 
            Format: [{{"keep_id": "ID", "delete_ids": ["ID1", "ID2"], "new_name": "Standardized Name"}}]
            
            Nodes:
            {node_list_str}
            """
            
            import ollama
            res = ollama.chat(model='llama3.2', messages=[{'role': 'user', 'content': pruning_prompt}], format='json')
            instructions = json.loads(res['message']['content'])
            
            # If the model returned a dict instead of a list
            if isinstance(instructions, dict): 
                instructions = instructions.get('merges', []) if 'merges' in instructions else [instructions]

            merge_count = 0
            for instr in instructions:
                keep_id = instr.get('keep_id')
                delete_ids = instr.get('delete_ids', [])
                new_name = instr.get('new_name')

                if not keep_id or not delete_ids: continue

                # Update the 'keep' node with the standardized name
                if new_name:
                    db.supabase.table("graph_nodes").update({"name": new_name}).eq("id", keep_id).execute()

                # Re-link and Delete
                for d_id in delete_ids:
                    self._relink_edges(d_id, keep_id)
                    db.supabase.table("graph_nodes").delete().eq("id", d_id).execute()
                    merge_count += 1
            
            return f"Success! Merged {merge_count} redundant nodes into master entities."
        except Exception as e:
            return f"Pruning Error: {e}"

graph_engine = GraphEngine()