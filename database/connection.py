import os
from supabase import create_client, Client
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.embeddings import HuggingFaceEmbeddings
from dotenv import load_dotenv

load_dotenv()

class DatabaseManager:
    def __init__(self):
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("Supabase credentials missing in .env")
        
        self.supabase: Client = create_client(url, key)
        
        # Local Embeddings (Safe and Fast)
        print("Loading local embedding model...")
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-mpnet-base-v2"
        )

        # Stable LLM
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-3-flash-preview",
            temperature=0,
            google_api_key=os.environ.get("GOOGLE_API_KEY")
        )

    def add_message(self, session_id: str, role: str, content: str):
        vector = self.embeddings.embed_query(content)
        data = {"session_id": session_id, "role": role, "content": content, "embedding": vector}
        return self.supabase.table("conversation_logs").insert(data).execute()

    def get_relevant_memories(self, session_id: str, query: str, limit: int = 5):
        query_vector = self.embeddings.embed_query(query)
        rpc_params = {
            'query_embedding': query_vector,
            'match_threshold': 0.25,
            'match_count': limit,
            'p_session_id': session_id
        }
        response = self.supabase.rpc('match_memories', rpc_params).execute()
        return response.data

    def add_structured_memory(self, session_id: str, memory_type: str, content: dict, confidence: float):
        memory_string = f"{memory_type}: {content.get('key')} is {content.get('value')}"
        vector = self.embeddings.embed_query(memory_string)
        data = {
            "session_id": session_id,
            "memory_type": memory_type,
            "content": content,
            "confidence": confidence,
            "embedding": vector
        }
        return self.supabase.table("user_memories").insert(data).execute()

db = DatabaseManager()