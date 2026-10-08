"""
Embedders
==========
Turns text into vectors. Two providers:

- fastembed: ONNX runtime, small install, the default for local (SQLite) use.
- sentence-transformers: PyTorch, GPU-capable, the default for Supabase.
"""

import logging
from typing import List

from dolphin_memory.config import DolphinConfig

logger = logging.getLogger("dolphin.store")


class FastEmbedEmbedder:
    """Embeddings via fastembed (ONNX, no PyTorch)."""

    def __init__(self, model_name: str):
        try:
            from fastembed import TextEmbedding
        except ImportError as e:
            raise ImportError(
                "The fastembed embedder needs the 'fastembed' package. "
                "Run: pip install fastembed"
            ) from e

        self.model_name = model_name
        self._model = TextEmbedding(model_name=model_name)

    def embed_query(self, text: str) -> List[float]:
        return next(iter(self._model.embed([text]))).tolist()


class SentenceTransformerEmbedder:
    """Embeddings via sentence-transformers (PyTorch)."""

    def __init__(self, model_name: str, device: str = "cpu"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                "The sentence-transformers embedder needs the 'sentence-transformers' "
                'package. Run: pip install "dolphin-memory[supabase]"'
            ) from e

        # Auto-detect GPU
        if device == "auto":
            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"

        self.model_name = model_name
        self._model = SentenceTransformer(model_name, device=device)
        logger.info(f"Embedding model loaded on {device}")

    def embed_query(self, text: str) -> List[float]:
        return self._model.encode(text).tolist()


def create_embedder(config: DolphinConfig):
    """Build the embedder selected by the config."""
    provider, model_name = config.resolved_embedding()
    logger.info(f"Loading embedding model: {model_name} ({provider})")
    if provider == "sentence-transformers":
        return SentenceTransformerEmbedder(model_name, config.embedding_device)
    return FastEmbedEmbedder(model_name)
