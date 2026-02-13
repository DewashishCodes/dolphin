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
        
        # Check for CUDA availability
        model_kwargs = {'device': 'cpu'}
        try:
            import torch
            if torch.cuda.is_available():
                model_kwargs = {'device': 'cuda'}
                print(f"✅ GPU Detected: {torch.cuda.get_device_name(0)}")
            else:
                print("⚠️ No GPU detected, using CPU.")
        except ImportError:
            pass

        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-mpnet-base-v2",
            model_kwargs=model_kwargs
        )

        # LLM initialized dynamically via get_llm()
        pass

    def get_llm(self, llm_config: dict):
        provider = llm_config.get('provider', 'gemini')
        api_key = llm_config.get('api_key')
        
        # Fallback to env if empty string or None
        if not api_key:
            if provider == 'gemini': api_key = os.environ.get("GOOGLE_API_KEY")
            elif provider == 'openai': api_key = os.environ.get("OPENAI_API_KEY")
            elif provider == 'groq': api_key = os.environ.get("GROQ_API_KEY")
            
        if not api_key and provider != 'ollama': # Ollama might not need key
             print(f"⚠️ Warning: No API Key found for {provider}")

        try:
            if provider == 'openai':
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(model="gpt-4o", temperature=0, api_key=api_key)
            elif provider == 'groq':
                from langchain_groq import ChatGroq
                return ChatGroq(model_name="llama3-70b-8192", temperature=0, groq_api_key=api_key)
            else: # Defaults to Gemini
                from langchain_google_genai import ChatGoogleGenerativeAI
                return ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0, google_api_key=api_key)
        except Exception as e:
            print(f"Error loading LLM {provider}: {e}")
            raise e

    def add_message(self, session_id: str, role: str, content: str):
        vector = self.embeddings.embed_query(content)
        data = {"session_id": session_id, "role": role, "content": content, "embedding": vector}
        return self.supabase.table("conversation_logs").insert(data).execute()

    def get_recent_messages(self, session_id: str, limit: int = 10):
        """Fetches the most recent messages for a session to maintain strict chronological context."""
        try:
            response = self.supabase.table("conversation_logs")\
                .select("role, content, created_at")\
                .eq("session_id", session_id)\
                .order("created_at", desc=True)\
                .limit(limit)\
                .execute()
            # Return reversed list so it reads chronologically (Old -> New)
            return response.data[::-1] if response.data else []
        except Exception as e:
            print(f"Error fetching recent messages: {e}")
            return []

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