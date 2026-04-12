"""
Dolphin V2 Database Connection
================================
Manages Supabase client, embeddings, and dynamic LLM instantiation.

V2 Changes:
- Structured logging replaces print() statements
- Better error propagation (no silent failures)
- Type hints throughout
"""

import os
import logging
from supabase import create_client, Client
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.embeddings import HuggingFaceEmbeddings
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("dolphin.db")


class DatabaseManager:
    """Central database and model connection manager."""

    def __init__(self):
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("Supabase credentials missing in .env (SUPABASE_URL, SUPABASE_KEY)")

        self.supabase: Client = create_client(url, key)
        logger.info("Supabase client initialized")

        # Local Embeddings
        logger.info("Loading local embedding model...")

        # Check for CUDA availability
        model_kwargs = {'device': 'cpu'}
        try:
            import torch
            if torch.cuda.is_available():
                model_kwargs = {'device': 'cuda'}
                logger.info(f"GPU detected: {torch.cuda.get_device_name(0)}")
            else:
                logger.info("No GPU detected, using CPU for embeddings")
        except ImportError:
            logger.info("PyTorch not installed, using CPU for embeddings")

        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-mpnet-base-v2",
            model_kwargs=model_kwargs
        )
        logger.info("Embedding model loaded successfully")

    def get_llm(self, llm_config: dict):
        """
        Dynamically instantiate an LLM based on the provided configuration.
        Supports: gemini, openai, groq, ollama.
        Falls back to environment API keys when not provided in config.
        """
        provider = llm_config.get('provider', 'gemini')
        api_key = llm_config.get('api_key')

        # Fallback to env if key not provided
        if not api_key:
            if provider == 'gemini':
                api_key = os.environ.get("GOOGLE_API_KEY")
            elif provider == 'openai':
                api_key = os.environ.get("OPENAI_API_KEY")
            elif provider == 'groq':
                api_key = os.environ.get("GROQ_API_KEY")

        if not api_key and provider != 'ollama':
            logger.warning(f"No API key found for provider '{provider}'")

        try:
            if provider == 'openai':
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(model="gpt-4o", temperature=0, api_key=api_key)
            elif provider == 'groq':
                from langchain_groq import ChatGroq
                return ChatGroq(model_name="llama3-70b-8192", temperature=0, groq_api_key=api_key)
            elif provider == 'ollama':
                from langchain_community.chat_models import ChatOllama
                return ChatOllama(model="llama3.2", temperature=0)
            else:  # Default to Gemini
                return ChatGoogleGenerativeAI(
                    model="gemini-2.5-flash",
                    temperature=0,
                    google_api_key=api_key
                )
        except Exception as e:
            logger.error(f"Failed to load LLM provider '{provider}': {e}")
            raise

    def add_message(self, session_id: str, role: str, content: str):
        """Log a message to the conversation history with its embedding."""
        try:
            vector = self.embeddings.embed_query(content)
            data = {
                "session_id": session_id,
                "role": role,
                "content": content,
                "embedding": vector
            }
            return self.supabase.table("conversation_logs").insert(data).execute()
        except Exception as e:
            logger.error(f"Failed to add message: {e}")
            raise

    def get_recent_messages(self, session_id: str, limit: int = 10) -> list:
        """Fetch the most recent messages for a session (chronological order)."""
        try:
            response = self.supabase.table("conversation_logs") \
                .select("role, content, created_at") \
                .eq("session_id", session_id) \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()
            # Reverse so oldest comes first (chronological reading order)
            return response.data[::-1] if response.data else []
        except Exception as e:
            logger.error(f"Failed to fetch recent messages: {e}")
            return []

    def get_relevant_memories(self, session_id: str, query: str, limit: int = 5) -> list:
        """Find semantically relevant memories using vector similarity search."""
        try:
            query_vector = self.embeddings.embed_query(query)
            rpc_params = {
                'query_embedding': query_vector,
                'match_threshold': 0.25,
                'match_count': limit,
                'p_session_id': session_id
            }
            response = self.supabase.rpc('match_memories', rpc_params).execute()
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Failed to search memories: {e}")
            return []

    def add_structured_memory(self, session_id: str, memory_type: str, content: dict, confidence: float):
        """Store a structured memory with its embedding and confidence score."""
        try:
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
        except Exception as e:
            logger.error(f"Failed to add structured memory: {e}")
            raise


db = DatabaseManager()