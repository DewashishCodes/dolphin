import hashlib
import math
import re

import pytest

from dolphin_memory import DolphinMemory


class FakeEmbedder:
    """Deterministic bag-of-words embedder, so tests need no model download."""

    DIMS = 64

    def embed_query(self, text):
        vec = [0.0] * self.DIMS
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.DIMS] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "dolphin.db")


@pytest.fixture
def make_memory(db_path):
    """Factory for DolphinMemory clients on a temp SQLite file with a fake embedder."""
    created = []

    def _make(triples=None, **kwargs):
        kwargs.setdefault("enable_background_extraction", False)
        memory = DolphinMemory(db_path=db_path, **kwargs)
        memory._store._embeddings = FakeEmbedder()
        # GraphEngine owns the extractor that add() uses
        memory._graph._extractor.extract = lambda text: list(triples or [])
        created.append(memory)
        return memory

    yield _make

    for memory in created:
        memory._executor.shutdown(wait=True)
        memory._store.backend.close()


@pytest.fixture
def memory(make_memory):
    return make_memory()
