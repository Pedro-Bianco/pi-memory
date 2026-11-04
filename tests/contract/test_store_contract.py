"""Every VectorStore implementation must pass this suite (docs/GUIA.md, section 15)."""

import importlib.util

import pytest

from pi_memory.engines.stores.memory import MemoryStore
from pi_memory.interfaces import Record
from pi_memory.search import BM25Index, hybrid, terms
from tests.fakes import FakeEmbedder

EMB = FakeEmbedder()


def _chroma(tmp_path):
    from pi_memory.engines.stores.chroma import ChromaStore
    return ChromaStore(path=str(tmp_path / "chroma"))


def _qdrant(tmp_path):
    from pi_memory.engines.stores.qdrant import QdrantStore
    return QdrantStore(path=str(tmp_path / "qdrant"))


FACTORIES = [pytest.param(lambda tmp_path: MemoryStore(), id="memory"),
             pytest.param(lambda tmp_path: MemoryStore(tmp_path / "m.json"), id="memory-file")]
if importlib.util.find_spec("qdrant_client"):
    FACTORIES.append(pytest.param(_qdrant, id="qdrant"))
if importlib.util.find_spec("chromadb"):
    FACTORIES.append(pytest.param(_chroma, id="chroma"))


@pytest.fixture(params=FACTORIES)
def store(request, tmp_path):
    instance = request.param(tmp_path)
    yield instance
    instance.close()


def rec(item_id, text, **payload):
    return Record(item_id, text, payload, EMB.embed_documents([text])[0], terms(text))


def test_open_collection_keeps_meta(store):
    meta = {"embedder": "fake", "dimension": EMB.dimension, "schema_version": 1}
    assert store.open_collection("colecao", EMB.dimension, meta) == meta
    other = {"embedder": "outro", "dimension": 3, "schema_version": 1}
    assert store.open_collection("colecao", 3, other) == meta  # existing meta wins; caller compares


def test_upsert_get_scan_count_delete(store):
    store.open_collection("colecao", EMB.dimension, {})
    store.upsert("colecao", [rec("m1", "Ana mora em Recife", owner="ana", topic="casa"),
                       rec("m2", "Ana gosta de café", owner="ana", topic="lazer",
                           metadata={"origem": "chat"}),
                       rec("m3", "Bruno joga xadrez", owner="bruno", topic="lazer")])
    assert [r.text for r in store.get("colecao", ["m2", "m1", "zz"])] == ["Ana gosta de café",
                                                                  "Ana mora em Recife"]
    assert store.get("colecao", ["m1"])[0].payload["topic"] == "casa"
    assert store.count("colecao", {"owner": "ana"}) == 2
    assert {r.id for r in store.scan("colecao", {"owner": "ana", "topic": "lazer"})} == {"m2"}
    assert {r.id for r in store.scan("colecao", {"metadata.origem": "chat"})} == {"m2"}
    assert len(store.scan("colecao", {}, limit=2)) == 2
    assert len(store.scan("colecao", {}, limit=2, offset=2)) == 1
    with_vectors = store.scan("colecao", {"owner": "bruno"}, with_vectors=True)[0]
    assert with_vectors.vector is not None and len(with_vectors.vector) == EMB.dimension

    store.upsert("colecao", [rec("m1", "Ana mora em Salvador", owner="ana", topic="casa")])
    assert store.get("colecao", ["m1"])[0].text == "Ana mora em Salvador"
    assert store.count("colecao", {}) == 3

    assert store.delete("colecao", ids=["m1", "nao-existe"]) == 1
    assert store.delete("colecao", where={"owner": "ana"}) == 1
    assert store.count("colecao", {}) == 1


def test_dense_search_orders_and_filters_by_owner(store):
    store.open_collection("colecao", EMB.dimension, {})
    store.upsert("colecao", [rec("a", "reunião de trabalho pela manhã", owner="ana"),
                       rec("b", "receita de bolo de cenoura", owner="ana"),
                       rec("c", "reunião de trabalho pela manhã", owner="bruno")])
    hits = store.dense_search("colecao", EMB.embed_query("reunião pela manhã"), {"owner": "ana"}, 5)
    assert [h.record.id for h in hits][0] == "a"
    assert "c" not in {h.record.id for h in hits}


def test_hybrid_finds_exact_code_first(store):
    store.open_collection("colecao", EMB.dimension, {})
    records = [rec("a", "contrato 2024-0815 de aluguel da casa", owner="ana"),
               rec("b", "contrato 2024-0816 de aluguel da casa", owner="ana"),
               rec("c", "contrato 2024-0816 de aluguel da casa", owner="bruno")]
    store.upsert("colecao", records)
    index = None
    if not store.native_hybrid:
        index = BM25Index()
        for r in records:
            index.add(r)
    query = "contrato 2024-0816"
    hits = hybrid(store, "colecao", EMB.embed_query(query), query, {"owner": "ana"}, 2, index)
    assert hits[0].record.id == "b"
    assert {h.record.id for h in hits} <= {"a", "b"}


def test_many_records_are_read_counted_and_deleted_in_full(store):
    """Large collections: Chroma failed reading 10 000 records in one call (too many SQL
    variables); every store must page internally."""
    store.open_collection("colecao", 8, {})
    vector = [1.0] + [0.0] * 7
    store.upsert("colecao", [Record(f"r{i}", f"texto {i}",
                                    {"owner": "ana" if i % 2 else "bruno"}, vector)
                             for i in range(1200)])
    assert len(store.scan("colecao", {})) == 1200
    assert len(store.scan("colecao", {}, limit=700, offset=600)) == 600
    assert store.count("colecao", {"owner": "ana"}) == 600
    assert len(store.get("colecao", [f"r{i}" for i in range(1100)])) == 1100
    assert store.delete("colecao", where={"owner": "bruno"}) == 600
    assert store.delete("colecao", ids=[f"r{i}" for i in range(1, 1200, 2)]) == 600
    assert store.count("colecao", {}) == 0
