import os
from supabase import create_client, Client
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from dotenv import load_dotenv
from google.genai import types

# Load env variables
load_dotenv()

class DatabaseManager:
    def __init__(self):
        # 1. Initialize Supabase
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("Supabase credentials missing in .env")
        
        self.supabase: Client = create_client(url, key)
        
        # 2. Initialize Gemini Embeddings (for vectorizing memory)
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001", 
            output_dimensionality=768  ,
            google_api_key=os.environ.get("GOOGLE_API_KEY")
        )

        # 3. Initialize Chat Model (for generation)
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0,
            google_api_key=os.environ.get("GOOGLE_API_KEY")
        )

    async def add_message(self, session_id: str, role: str, content: str):
        """
        Saves a message to Supabase and generates its embedding.
        """
        # Generate embedding for the text
        vector = self.embeddings.embed_query(content)
        
        data = {
            "session_id": session_id,
            "role": role,
            "content": content,
            "embedding": vector
        }
        
        # Insert into DB
        response = self.supabase.table("conversation_logs").insert(data).execute()
        return response

    async def get_recent_history(self, session_id: str, limit: int = 5):
        """
        Simple fetch of the last N messages (Short-term memory)
        """
        response = self.supabase.table("conversation_logs")\
            .select("role, content")\
            .eq("session_id", session_id)\
            .order("created_at", desc=True)\
            .limit(limit)\
            .execute()
        
        # Return in reverse order (chronological)
        return response.data[::-1] if response.data else []
    
    async def get_relevant_memories(self, session_id: str, query: str, limit: int = 3):
        """
        Search structured memories using semantic similarity.
        """
    # 1. Vectorize the user's current query
        query_vector = self.embeddings.embed_query(query)

    # 2. Call the RPC function we created in SQL in Phase 1
    # Note: We need a slight variation for the 'user_memories' table
    # Let's use a direct RPC call via Supabase
        rpc_params = {
        'query_embedding': query_vector,
        'match_threshold': 0.5, # Adjust based on testing
        'match_count': limit,
        'p_session_id': session_id
        }
    
    # We will use the 'match_memories' function (we'll create this SQL in a second)
        response = self.supabase.rpc('match_memories', rpc_params).execute()
        return response.data

    async def add_structured_memory(self, session_id: str, memory_type: str, content: dict, confidence: float):
        """
        Saves a structured fact (JSON) to the user_memories table.
        """
    # Create a string representation for the embedding
    # Example: "preference: language is Kannada"
        memory_string = f"{memory_type}: {content.get('key')} is {content.get('value')}"
        vector = self.embeddings.embed_query(memory_string)

        data = {
        "session_id": session_id,
        "memory_type": memory_type,
        "content": content,
        "confidence": confidence,
        "embedding": vector,
        "last_accessed": "now()"
        }

        response = self.supabase.table("user_memories").insert(data).execute()
        return response

# Singleton instance
db = DatabaseManager()