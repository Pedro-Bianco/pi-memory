"""Knowledge base administration: collections, documents, chunks and the owner overview."""

import pytest

from pi_memory import InvalidInputError, NotFoundError
from tests.fakes import make_pm

TEXT = "Primeira frase do manual. Segunda frase. Terceira. Quarta. Quinta. Sexta. Sétima. Oitava."


@pytest.fixture
def pm():
    with make_pm() as instance:
        yield instance


def test_same_file_in_two_collections_are_two_documents(pm):
    a = pm.documents.add_bytes("manual.txt", TEXT.encode(), "ana", collection="contratos")
    b = pm.documents.add_bytes("manual.txt", TEXT.encode(), "ana", collection="manuais")
    c = pm.documents.add_bytes("leia.txt", b"Texto solto aqui.", "ana")
    assert a["document"]["id"] != b["document"]["id"]
    assert c["document"]["collection"] == "geral"
    assert [x["name"] for x in pm.documents.collections("ana")["collections"]] == [
        "contratos", "geral", "manuais"]
    assert len(pm.documents.list("ana", collection="manuais")["documents"]) == 1
    hits = pm.documents.search("manual", "ana", collection="contratos")["results"]
    assert {h["citation"]["collection"] for h in hits} == {"contratos"}


def test_invalid_collection_name(pm):
    with pytest.raises(InvalidInputError, match="coleção"):
        pm.documents.add_bytes("a.txt", b"x y.", "ana", collection="../../etc")


def test_delete_collection_only_that_one(pm):
    pm.documents.add_bytes("a.txt", TEXT.encode(), "ana", collection="velha")
    pm.documents.add_bytes("b.txt", TEXT.encode(), "ana", collection="velha")
    pm.documents.add_bytes("c.txt", TEXT.encode(), "ana", collection="nova")
    pm.documents.add_bytes("d.txt", TEXT.encode(), "bruno", collection="velha")
    result = pm.documents.delete_collection("velha", "ana")
    assert result["deleted_documents"] == 2 and result["deleted_chunks"] >= 2
    assert [c["name"] for c in pm.documents.collections("ana")["collections"]] == ["nova"]
    assert pm.documents.collections("bruno")["collections"][0]["name"] == "velha"
    assert all(h["citation"]["collection"] == "nova"
               for h in pm.documents.search("manual", "ana")["results"])
    with pytest.raises(NotFoundError):
        pm.documents.delete_collection("velha", "ana")


def test_add_text_creates_a_searchable_document(pm):
    r = pm.documents.add_text("Senha do wifi", "A senha fica escrita na geladeira.", "ana",
                              collection="casa")
    assert r["document"]["source"] == "Senha do wifi.md"
    hit = pm.documents.search("onde fica a senha?", "ana")["results"][0]
    assert hit["citation"]["label"] == "Senha do wifi.md, seção Senha do wifi"
    with pytest.raises(InvalidInputError):
        pm.documents.add_text("", "x", "ana")


def test_document_with_chunks_and_single_chunk_deletion(pm):
    long_text = " ".join(f"Frase número {i}." for i in range(1, 30))
    doc = pm.documents.add_bytes("longo.txt", long_text.encode(), "ana")["document"]
    full = pm.documents.get(doc["id"], "ana")
    assert full["document"]["chunks"] == len(full["chunks"]) == doc["chunks"] > 2
    assert [c["index"] for c in full["chunks"]] == list(range(doc["chunks"]))
    first = full["chunks"][0]
    assert pm.documents.chunk(first["id"], "ana")["text"] == first["text"]
    assert pm.documents.delete_chunk(first["id"], "ana") == {"deleted": 1}
    listed = pm.documents.list("ana")["documents"]
    assert listed[0]["id"] == doc["id"]                         # still listed without chunk 0
    assert listed[0]["chunks"] == doc["chunks"] - 1
    assert pm.documents.chunks("ana", doc_id=doc["id"])["total"] == doc["chunks"] - 1
    assert pm.documents.chunks("ana", limit=2)["chunks"].__len__() == 2
    with pytest.raises(NotFoundError):
        pm.documents.chunk(first["id"], "ana")
    with pytest.raises(NotFoundError):
        pm.documents.delete_chunk(full["chunks"][1]["id"], "bruno")      # other owner


def test_stats_overview(pm):
    pm.memories.remember("O usuário gosta de jazz", "ana", topic="lazer")
    pm.memories.remember("O usuário corre", "ana", topic="saúde")
    pm.documents.add_bytes("a.txt", TEXT.encode(), "ana", collection="manuais")
    s = pm.stats("ana")
    assert s["memories"] == {"total": 2, "by_topic": {"lazer": 1, "saúde": 1}}
    assert s["documents"] == 1 and s["chunks"] >= 1
    assert s["collections"][0]["name"] == "manuais"
    assert s["engines"]["embedder"] == "fake:bow64" and s["engines"]["store"] == "MemoryStore"
    assert pm.stats("ninguem")["memories"]["total"] == 0


def test_graph_with_knowledge_base(pm):
    pm.memories.remember("O usuário gosta de jazz", "ana", topic="lazer")
    pm.documents.add_bytes("a.txt", TEXT.encode(), "ana", collection="manuais")
    plain = pm.graph.data("ana")
    assert {n["kind"] for n in plain["nodes"]} == {"topic", "memory"}
    full = pm.graph.data("ana", include_documents=True, include_chunks=True)
    kinds = {n["kind"] for n in full["nodes"]}
    assert kinds == {"topic", "memory", "collection", "document", "chunk"}
    contains = [e for e in full["edges"] if e["kind"] == "contains"]
    assert any(e["target"] == "c:manuais" for e in contains)
    assert any(e["source"].startswith("k:") for e in contains)
