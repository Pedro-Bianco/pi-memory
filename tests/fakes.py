"""Engines for tests: no network, no models, deterministic."""

from __future__ import annotations

import atexit
import math
import os
import re
import shutil
import tempfile
import zlib
from collections.abc import Callable

from pi_memory import PiMemory
from pi_memory._util import plain
from pi_memory.engines.stores.memory import MemoryStore


class FakeEmbedder:
    """Bag of words hashed into `dimension` slots: texts sharing words are close."""

    def __init__(self, dimension: int = 64, name: str = "fake:bow"):
        self.name = f"{name}{dimension}"
        self.dimension = dimension

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for word in re.findall(r"\w+", plain(text)):
            if len(word) > 2:
                vector[zlib.crc32(word.encode()) % self.dimension] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class ScriptedLLM:
    """Answers with `handler(prompt)` or, without one, pops answers from `replies` in order.
    Every prompt received is kept in `prompts`."""

    def __init__(self, replies: list[str] | None = None,
                 handler: Callable[[str], str] | None = None):
        self.replies = list(replies or [])
        self.handler = handler
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.handler is not None:
            return self.handler(prompt)
        if not self.replies:
            raise AssertionError(f"ScriptedLLM sem resposta para:\n{prompt[:300]}")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def store_for_tests():
    """The store the flow tests run on: PI_MEMORY_TEST_STORE=memory (default) | qdrant | chroma.
    tests/contract/test_flows_all_stores.py runs the flow tests once per installed store."""
    kind = os.environ.get("PI_MEMORY_TEST_STORE", "memory")
    if kind == "memory":
        return MemoryStore()
    folder = tempfile.mkdtemp(prefix="pi_memory_test_")
    atexit.register(shutil.rmtree, folder, True)
    if kind == "qdrant":
        from pi_memory.engines.stores.qdrant import QdrantStore
        return QdrantStore(path=folder)
    if kind == "chroma":
        from pi_memory.engines.stores.chroma import ChromaStore
        return ChromaStore(path=folder)
    raise ValueError(f"PI_MEMORY_TEST_STORE desconhecido: {kind}")


def make_pm(**overrides) -> PiMemory:
    options = {"embedder": FakeEmbedder(), "llm": ScriptedLLM()}
    if "store" not in overrides:
        options["store"] = store_for_tests()
    options.update(overrides)
    return PiMemory(**options)
