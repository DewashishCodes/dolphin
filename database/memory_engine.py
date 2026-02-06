import json
from datetime import datetime, timezone
import dateutil.parser
from database.connection import db

def ensure_string(content):
    """Safety helper to handle Gemini's potential list-type content."""
    if isinstance(content, list):
        # Extract text from the first block if it's a list
        return content[0].get('text', str(content))
    return str(content)

class MemoryEngine:
    def extract_and_store(self, session_id: str, text: str):
        prompt = f"Identify long-term facts (Preferences, Facts, Constraints) from: {text}. Return ONLY a JSON list of objects with type, key, value, confidence."
        try:
            response = db.llm.invoke(prompt)
            # SAFETY CHECK: Ensure content is a string
            raw_text = ensure_string(response.content)
            
            cleaned = raw_text.replace("```json", "").replace("```", "").strip()
            memories = json.loads(cleaned)
            
            for mem in memories:
                db.add_structured_memory(
                    session_id, 
                    mem.get('type', 'fact'), 
                    {"key": mem.get('key'), "value": mem.get('value')}, 
                    mem.get('confidence', 0.9)
                )
            return memories
        except Exception as e:
            print(f"Extraction Error: {e}")
            return []

class ChatEngine:
    def get_relative_time(self, timestr):
        try:
            past = dateutil.parser.isoparse(timestr)
            diff = datetime.now(timezone.utc) - past
            m = int(diff.total_seconds() // 60)
            if m < 1: return "Just now"
            if m < 60: return f"{m}m ago"
            h = m // 60
            if h < 24: return f"{h}h ago"
            return f"{h//24}d ago"
        except: return "Recently"

    def generate_response(self, session_id: str, user_input: str):
        # 1. Query Expansion for better retrieval
        exp_p = f"Suggest 3 search keywords for a memory vault to help answer: {user_input}"
        search_terms = ensure_string(db.llm.invoke(exp_p).content)
        
        # 2. Search & Format
        memories = db.get_relevant_memories(session_id, f"{user_input} {search_terms}")
        context = "### USER MEMORY LOGS ###\n"
        if memories:
            sorted_m = sorted(memories, key=lambda x: x['created_at'])
            for m in sorted_m:
                rel = self.get_relative_time(m['created_at'])
                c = m.get('content', {})
                context += f"- [{rel}] {c.get('key')}: {c.get('value')}\n"
        else:
            context += "No previous memories found.\n"

        # 3. Final System Prompt
        sys_p = f"""
        {context}
        
        You are a personalized assistant. Use the memories above to answer. 
        If memories conflict, prefer the one with the most recent timestamp.
        
        User: {user_input}
        """
        
        res = db.llm.invoke(sys_p)
        final_text = ensure_string(res.content)
        return final_text, memories

memory_engine = MemoryEngine()
chat_engine = ChatEngine()