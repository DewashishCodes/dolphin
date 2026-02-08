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

    def extract_and_sync_graph(self, session_id, text):
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

            # Ensure 'User' node exists
            self._upsert_node(session_id, "User", "Person")

            results = []
            for item in triples:
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
                ).eq("source_id", u_id).limit(10).execute()
                
                for e in edges.data:
                    target = e['graph_nodes']
                    context_strings.append(f"User {e['relationship']} {target['name']} ({target['label']})")

            # 2. SEMANTIC NODE SEARCH (The Revolutionary Part)
            # Find nodes that match the query even if they aren't connected to the 'User' yet
            query_vec = db.embeddings.embed_query(query)
            semantic_nodes = db.supabase.rpc('match_graph_nodes', {
                'query_embedding': query_vec,
                'match_threshold': 0.3,
                'match_count': 5,
                'p_session_id': session_id
            }).execute()

            for node in semantic_nodes.data:
                context_strings.append(f"Relevant Topic: {node['name']} ({node['label']})")

            # 3. GLOBAL FALLBACK: If the graph is small, just grab the last 10 nodes
            if len(context_strings) < 3:
                recent = db.supabase.table("graph_nodes").select("name, label").eq("session_id", session_id).limit(10).execute()
                for r in recent.data:
                    context_strings.append(f"Known Fact: {r['name']} is a {r['label']}")

            return "\n".join(list(set(context_strings))) # Deduplicate
        except Exception as e:
            print(f"Graph Retrieval Error: {e}")
            return ""

graph_engine = GraphEngine()