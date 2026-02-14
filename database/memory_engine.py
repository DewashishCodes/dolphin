import json
from datetime import datetime, timezone
import dateutil.parser
from database.connection import db
from database.graph_engine import graph_engine

def ensure_string(content):
    """Deep cleanup to remove 'signature' and block-metadata from Gemini."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # Extract only the 'text' part from the first element if it exists
        first = content[0]
        if isinstance(first, dict) and 'text' in first:
            return first['text']
        return str(first)
    if isinstance(content, dict) and 'text' in content:
        return content['text']
    return str(content)

class MemoryEngine:
    def extract_and_store(self, session_id: str, text: str):
        return graph_engine.extract_and_sync_graph(session_id, text)

class ChatEngine:
    def get_relative_time(self, timestr):
        try:
            past = dateutil.parser.isoparse(timestr)
            diff = datetime.now(timezone.utc) - past
            m = int(diff.total_seconds() // 60)
            if m < 1: return "Just now"
            if m < 60: return f"{m}m ago"
            h = m // 60
            return f"{h}h ago" if h < 24 else f"{h//24}d ago"
        except: return "Recently"

    def generate_response(self, session_id: str, user_input: str, llm_config: dict = None):
        # 1. Fetch Context (Hybrid Retrieval)
        # A. Working Memory: Recent 10 messages (Chronological)
        recent_history = db.get_recent_messages(session_id, limit=10)
        
        # B. Long-Term Memory: Semantic search (Relevant facts from past)
        relevant_memories = db.get_relevant_memories(session_id, user_input, limit=10)
        
        # C. Graph Context: Structured Relationships
        graph_text = graph_engine.get_graph_context(session_id, user_input)
        print(f"DEBUG: Graph Text Content (First 200 chars): {graph_text[:200]}")
        
        # 2. Build the "Intelligence Context"
        # Format recent history
        history_str = ""
        for msg in recent_history:
            history_str += f"- {msg.get('role').upper()}: {msg.get('content')}\n"

        # Format relevant memories
        memory_str = ""
        for l in relevant_memories:
            c = l.get('content', {})
            # Handle both string content and dict content
            val = c.get('value') if isinstance(c, dict) else str(c)
            key = c.get('key') if isinstance(c, dict) else "Memory"
            memory_str += f"- {key}: {val}\n"

        # 3. Construct an ASSERTIVE prompt
        prompt = f"""
        System: You are Dolphin. You have a PERMANENT KNOWLEDGE GRAPH about the user.
        
        --- WORKING MEMORY (Recent Conversation) ---
        {history_str}
        
        --- LONG-TERM MEMORY (Relevant Facts) ---
        {memory_str}
        
        --- KNOWLEDGE GRAPH (Structured Facts) ---
        {graph_text}
        
        INSTRUCTIONS:
        1. Use 'Working Memory' to maintain conversation flow.
        2. Use 'Long-Term Memory' and 'Knowledge Graph' to recall past facts (e.g., location, preferences).
        3. If the graph contains a location (like Pune), assume the user is THERE right now.
        4. If the user mentions 'stress' or 'deadline', link it to their 'Software Engineer' role and 'Friday' deadline found in the graph.
        5. DO NOT ask the user for their city or name. You already have them in your graph. 
        6. Use the facts to give a hyper-personalized recommendation.
        
        User Query: {user_input}
        """
        
        llm = db.get_llm(llm_config if llm_config else {})
        res = llm.invoke(prompt)
        
        # Return the response AND the combined memory context for the UI
        memories_list = []
        for l in relevant_memories:
            c = l.get('content', {})
            val = c.get('value') if isinstance(c, dict) else str(c)
            key = c.get('key') if isinstance(c, dict) else "Memory"
            memories_list.append(f"{key}: {val}")
            
        if graph_text:
             for line in graph_text.splitlines():
                 if line.strip():
                     memories_list.append(f"🕸️ {line.strip()}")
        
        print(f"DEBUG: Final Memories List sent to UI: {memories_list}")

        return ensure_string(res.content), memories_list

memory_engine = MemoryEngine()
chat_engine = ChatEngine()