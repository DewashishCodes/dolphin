"""
Dolphin Configuration
======================
Manages all configurable parameters for the Dolphin memory system.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DolphinConfig:
    """Configuration for the Dolphin memory system.

    Args:
        supabase_url: Your Supabase project URL
        supabase_key: Your Supabase anon/service key
        ollama_model: Local model for triple extraction (default: llama3.2)
        embedding_model: Sentence-transformer model for embeddings (default: all-mpnet-base-v2)
        embedding_device: Device for embedding model ('cpu' or 'cuda')
        extraction_provider: 'ollama' (default) or 'gemini'/'openai' for cloud
        cloud_api_key: API key for cloud LLM (only needed if extraction_provider is cloud)
        similarity_threshold: Minimum similarity score for memory retrieval (0.0-1.0)
        max_graph_context: Maximum number of graph facts to retrieve per query
        max_memory_results: Maximum number of semantic memory results per query
        auto_extract: Whether to automatically extract triples when adding memories
    """
    supabase_url: str = ""
    supabase_key: str = ""

    # Local LLM (primary — saves tokens)
    ollama_model: str = "llama3.2"

    # Embeddings
    embedding_model: str = "sentence-transformers/all-mpnet-base-v2"
    embedding_device: str = "cpu"

    # Extraction
    extraction_provider: str = "ollama"  # 'ollama', 'gemini', 'openai'
    cloud_api_key: Optional[str] = None

    # Retrieval
    similarity_threshold: float = 0.25
    max_graph_context: int = 15
    max_memory_results: int = 10

    # Behavior
    auto_extract: bool = True

    def validate(self):
        """Validate that required configuration is present."""
        errors = []
        if not self.supabase_url:
            errors.append("supabase_url is required")
        if not self.supabase_key:
            errors.append("supabase_key is required")
        if errors:
            raise ValueError(f"Invalid DolphinConfig: {'; '.join(errors)}")
