"""
Dolphin Configuration
======================
Manages all configurable parameters for the Dolphin memory system.
"""

import os
from dataclasses import dataclass
from typing import Optional, Tuple

BACKENDS = ("auto", "sqlite", "supabase")
EMBEDDING_PROVIDERS = ("auto", "fastembed", "sentence-transformers")
EXTRACTION_PROFILES = ("personal", "agent")

# Both are sentence-transformers models with similar score distributions, so the
# similarity thresholds below hold for either.
DEFAULT_FASTEMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"  # 384 dims, ONNX
DEFAULT_ST_MODEL = "sentence-transformers/all-mpnet-base-v2"  # 768 dims, matches schema.sql


@dataclass
class DolphinConfig:
    """Configuration for the Dolphin memory system.

    Args:
        backend: 'sqlite' (local file), 'supabase', or 'auto' (Supabase if a
            supabase_url is given, otherwise SQLite)
        db_path: SQLite database file (only used by the sqlite backend)
        supabase_url: Your Supabase project URL
        supabase_key: Your Supabase anon/service key
        ollama_model: Local model for triple extraction (default: llama3.2)
        embedding_provider: 'fastembed', 'sentence-transformers', or 'auto'
            (sentence-transformers for Supabase, fastembed for SQLite)
        embedding_model: Embedding model name (default depends on the provider)
        embedding_device: Device for sentence-transformers ('cpu', 'cuda' or 'auto')
        extraction_provider: 'ollama' (default) or 'gemini'/'openai' for cloud
        extraction_profile: 'personal' (facts about a person, the default) or
            'agent' (project knowledge recorded by coding agents)
        cloud_api_key: API key for cloud LLM (only needed if extraction_provider is cloud)
        similarity_threshold: Minimum similarity score for memory retrieval (0.0-1.0)
        max_graph_context: Maximum number of graph facts to retrieve per query
        max_memory_results: Maximum number of semantic memory results per query
        auto_extract: Whether to automatically extract triples when adding memories
    """
    # Storage
    backend: str = "auto"
    db_path: str = "~/.dolphin/dolphin.db"
    supabase_url: str = ""
    supabase_key: str = ""

    # Local LLM (primary — saves tokens)
    ollama_model: str = "llama3.2"

    # Embeddings
    embedding_provider: str = "auto"
    embedding_model: Optional[str] = None
    embedding_device: str = "cpu"

    # Extraction
    extraction_provider: str = "ollama"  # 'ollama', 'gemini', 'openai'
    extraction_profile: str = "personal"  # 'personal', 'agent'
    cloud_api_key: Optional[str] = None

    # Deduplication
    deduplicate: bool = True
    dedupe_threshold: float = 0.92

    # Retrieval
    similarity_threshold: float = 0.20
    max_graph_context: int = 15
    max_memory_results: int = 10

    # Behavior
    auto_extract: bool = True
    enable_background_extraction: bool = True

    @classmethod
    def from_env(cls) -> "DolphinConfig":
        """
        Build a config from environment variables (used by the `dolphin` CLI).

        DOLPHIN_BACKEND, DOLPHIN_DB_PATH, SUPABASE_URL, SUPABASE_KEY,
        DOLPHIN_EMBEDDING_PROVIDER, DOLPHIN_EMBEDDING_MODEL,
        DOLPHIN_EXTRACTION_PROVIDER, DOLPHIN_EXTRACTION_PROFILE,
        DOLPHIN_CLOUD_API_KEY, DOLPHIN_OLLAMA_MODEL
        """
        env_fields = {
            "DOLPHIN_BACKEND": "backend",
            "DOLPHIN_DB_PATH": "db_path",
            "SUPABASE_URL": "supabase_url",
            "SUPABASE_KEY": "supabase_key",
            "DOLPHIN_EMBEDDING_PROVIDER": "embedding_provider",
            "DOLPHIN_EMBEDDING_MODEL": "embedding_model",
            "DOLPHIN_EXTRACTION_PROVIDER": "extraction_provider",
            "DOLPHIN_EXTRACTION_PROFILE": "extraction_profile",
            "DOLPHIN_CLOUD_API_KEY": "cloud_api_key",
            "DOLPHIN_OLLAMA_MODEL": "ollama_model",
        }
        values = {
            field: os.environ[var] for var, field in env_fields.items() if os.environ.get(var)
        }
        return cls(**values)

    @classmethod
    def for_agents(cls) -> "DolphinConfig":
        """from_env(), with the agent extraction profile unless the environment picks one."""
        config = cls.from_env()
        if not os.environ.get("DOLPHIN_EXTRACTION_PROFILE"):
            config.extraction_profile = "agent"
        return config

    def resolved_backend(self) -> str:
        """The backend to use once 'auto' is resolved."""
        if self.backend != "auto":
            return self.backend
        return "supabase" if self.supabase_url else "sqlite"

    def resolved_embedding(self) -> Tuple[str, str]:
        """(provider, model name) once 'auto' and the default model are resolved."""
        provider = self.embedding_provider
        if provider == "auto":
            # The Supabase schema has 768-dim vector columns
            provider = (
                "sentence-transformers" if self.resolved_backend() == "supabase"
                else "fastembed"
            )
        model = self.embedding_model or (
            DEFAULT_ST_MODEL if provider == "sentence-transformers"
            else DEFAULT_FASTEMBED_MODEL
        )
        return provider, model

    def validate(self):
        """Validate that required configuration is present."""
        errors = []
        if self.backend not in BACKENDS:
            errors.append(f"backend must be one of {BACKENDS}")
        if self.embedding_provider not in EMBEDDING_PROVIDERS:
            errors.append(f"embedding_provider must be one of {EMBEDDING_PROVIDERS}")
        if self.extraction_profile not in EXTRACTION_PROFILES:
            errors.append(f"extraction_profile must be one of {EXTRACTION_PROFILES}")
        if self.resolved_backend() == "supabase":
            if not self.supabase_url:
                errors.append("supabase_url is required")
            if not self.supabase_key:
                errors.append("supabase_key is required")
        if errors:
            raise ValueError(f"Invalid DolphinConfig: {'; '.join(errors)}")
