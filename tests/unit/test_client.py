import pytest

from pi_memory import EmbedderMismatchError, PiMemory
from pi_memory.engines.stores.memory import MemoryStore
from tests.fakes import FakeEmbedder, ScriptedLLM


def test_opens_both_collections_with_embedder_meta():
    store = MemoryStore()
    with PiMemory(embedder=FakeEmbedder(), llm=ScriptedLLM(), store=store) as pm:
        meta = store.open_collection(pm.memories_collection, 1, {})
        assert meta["embedder"] == "fake:bow64"
        assert meta["dimension"] == 64
        assert store.count(pm.chunks_collection, {}) == 0


def test_other_embedder_on_same_store_is_refused_in_portuguese(tmp_path):
    path = tmp_path / "m.json"
    PiMemory(embedder=FakeEmbedder(), llm=ScriptedLLM(), store=MemoryStore(path)).close()
    with pytest.raises(EmbedderMismatchError) as info:
        PiMemory(embedder=FakeEmbedder(dimension=32), llm=ScriptedLLM(), store=MemoryStore(path))
    assert "fake:bow64" in info.value.message and "fake:bow32" in info.value.message
    assert "reindex" in info.value.message


def test_a_plain_function_is_accepted_as_llm():
    with PiMemory(embedder=FakeEmbedder(), llm=lambda prompt: "NULO", store=MemoryStore()) as pm:
        assert pm.llm.complete("x") == "NULO"


def test_close_closes_the_store():
    closed = []

    class Store(MemoryStore):
        def close(self):
            closed.append(True)

    with PiMemory(embedder=FakeEmbedder(), llm=ScriptedLLM(), store=Store()):
        pass
    assert closed == [True]
