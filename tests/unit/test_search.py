from pi_memory.engines.stores.memory import MemoryStore
from pi_memory.interfaces import Record
from pi_memory.search import BM25Index, dbsf_fuse, hybrid, terms, tokens
from tests.fakes import FakeEmbedder


def test_tokens_keep_codes_whole_and_split():
    assert tokens("Nota NF-4521, cláusula 7.2") == [
        "nota", "nf-4521", "clausula", "7.2", "nf", "4521"]


def test_bm25_ranks_exact_code_first_and_filters():
    index = BM25Index()
    index.add(Record("a", "contrato 2024-0815 de aluguel", {"owner": "ana"}))
    index.add(Record("b", "contrato 2024-0816 de aluguel", {"owner": "ana"}))
    index.add(Record("c", "contrato 2024-0815 de aluguel", {"owner": "bruno"}))
    ranked = index.search(terms("2024-0815"), {"owner": "ana"}, 5)
    assert ranked[0][0] == "a"
    assert "c" not in [i for i, _ in ranked]
    index.remove(["a"])
    assert "a" not in [i for i, _ in index.search(terms("2024-0815"), {"owner": "ana"}, 5)]
    assert index.search(terms("aluguel"), {"owner": "ninguem"}, 5) == []


def test_dbsf_sums_normalized_scores():
    fused = dbsf_fuse([[("x", 0.9), ("y", 0.8), ("z", 0.1)], [("y", 10.0), ("w", 1.0)]], 10)
    ids = [i for i, _ in fused]
    assert ids[0] == "y"
    assert set(ids) == {"x", "y", "z", "w"}


def test_hybrid_on_store_without_native_hybrid_finds_the_exact_code():
    store, embedder = MemoryStore(), FakeEmbedder()
    store.open_collection("c", embedder.dimension, {})
    index = BM25Index()
    texts = {"a": "contrato 2024-0815 de aluguel da casa",
             "b": "contrato 2024-0816 de aluguel da casa",
             "c": "receita de bolo de cenoura"}
    records = [Record(i, t, {"owner": "ana"}, embedder.embed_documents([t])[0])
               for i, t in texts.items()]
    store.upsert("c", records)
    for r in records:
        index.add(r)
    query = "contrato 2024-0816"
    hits = hybrid(store, "c", embedder.embed_query(query), query, {"owner": "ana"}, 3, index)
    assert hits[0].record.id == "b"
    assert hits[0].score >= hits[1].score
