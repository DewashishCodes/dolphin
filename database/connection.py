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

# Singleton instance
db = DatabaseManager()