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

    def generate_response(self, session_id: str, user_input: str):
        # 1. Fetch Context
        logs = db.get_relevant_memories(session_id, user_input, limit=2)
        graph = graph_engine.get_graph_context(session_id, user_input)
        
        # 2. Build the "Intelligence Context"
        full_ctx = f"--- KNOWLEDGE GRAPH ---\n{graph}\n\n--- RECENT CHAT LOGS ---\n"
        for l in logs:
            c = l.get('content', {})
            full_ctx += f"- {c.get('key')}: {c.get('value')}\n"

        # 3. Construct an ASSERTIVE prompt
        prompt = f"""
        System: You are Dolphin. You have a PERMANENT KNOWLEDGE GRAPH about the user.
        
        FACTS YOU ALREADY KNOW:
        {full_ctx}
        
        INSTRUCTIONS:
        1. If the graph contains a location (like Pune), assume the user is THERE right now.
        2. If the user mentions 'stress' or 'deadline', link it to their 'Software Engineer' role and 'Friday' deadline found in the graph.
        3. DO NOT ask the user for their city or name. You already have them in your graph. 
        4. Use the facts to give a hyper-personalized recommendation.
        
        User Query: {user_input}
        """
        
        res = db.llm.invoke(prompt)
        return ensure_string(res.content), graph

memory_engine = MemoryEngine()
chat_engine = ChatEngine()