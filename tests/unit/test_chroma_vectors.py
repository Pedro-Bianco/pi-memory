"""Chroma 1.5.x sometimes cannot read vectors back ("Nothing found on disk"): the graph then comes
without "similar" links and a warning, instead of failing (engines/stores/chroma.py)."""

import importlib.util
import tempfile

import pytest

from tests.fakes import FakeEmbedder, ScriptedLLM

pytestmark = pytest.mark.skipif(not importlib.util.find_spec("chromadb"),
                                reason="extra chroma não instalado")


def chroma_pm():
    from pi_memory import PiMemory
    from pi_memory.engines.stores.chroma import ChromaStore

    pm = PiMemory(embedder=FakeEmbedder(), llm=ScriptedLLM(),
                  store=ChromaStore(path=tempfile.mkdtemp(prefix="pi_memory_test_")))
    for text in ("O usuário tem uma gata", "O usuário tem um gato", "O usuário tem um cão"):
        pm.memories.remember(text, owner="ana", topic="animais")
    return pm


def break_vectors(pm, monkeypatch, message):
    pages = pm.store._pages

    def failing(col, where, include, *args):
        if "embeddings" in include:
            raise RuntimeError(message)
        return pages(col, where, include, *args)

    monkeypatch.setattr(pm.store, "_pages", failing)


def test_graph_without_vectors_warns_and_keeps_the_rest(monkeypatch):
    pm = chroma_pm()
    assert any(e["kind"] == "similar" for e in pm.graph.data("ana")["edges"])
    break_vectors(pm, monkeypatch, "Error executing plan: Internal error: Error creating hnsw "
                                   "segment reader: Nothing found on disk")
    with pytest.warns(RuntimeWarning, match="sem eles"):
        graph = pm.graph.data("ana")
    assert sum(n["kind"] == "memory" for n in graph["nodes"]) == 3
    assert {e["kind"] for e in graph["edges"]} == {"belongs"}


def test_other_errors_still_fail(monkeypatch):
    pm = chroma_pm()
    break_vectors(pm, monkeypatch, "disk full")
    with pytest.raises(RuntimeError, match="disk full"):
        pm.graph.data("ana")
