"""One owner never sees or changes another owner's data, in any operation and any transport.

Two owners share one store, with colliding names on purpose (same topic, same collection, same
document file name). Owner "bruno" then calls all the operations, by id and by name, aiming at
owner "ana": nothing of ana's may come back, and ana's data must be exactly the same afterwards.
Also runs on Qdrant and Chroma (tests/contract/test_flows_all_stores.py)."""

import base64
import importlib.util
import json

import pytest

from pi_memory.operations import OPERATIONS, dispatch
from tests.fakes import ScriptedLLM, make_pm
from tests.transports import via_cli, via_dispatch, via_http, via_mcp
from tests.unit.test_memories import router

MARK = "zarabatana"      # appears only in ana's data


def b64(text):
    return base64.b64encode(text.encode()).decode()


def seeded():
    """A store with ana's and bruno's data, and the ids of ana's records."""
    llm = ScriptedLLM(handler=router(extraction="FATO: O usuário toca violão", topics="1. lazer",
                                     decisions=["DELETE 1"] * 10))
    pm = make_pm(llm=llm)
    for text, topic in [(f"O usuário guarda a {MARK} na garagem", "casa"),
                        (f"O usuário toca {MARK} aos domingos", "lazer")]:
        pm.memories.remember(text, owner="ana", topic=topic)
    pm.documents.add_text("Notas", f"A {MARK} fica no armário.", owner="ana")
    pm.documents.add_bytes("ata.md", f"# Ata\n\nA {MARK} foi aprovada.".encode(), owner="ana",
                           collection="atas")
    pm.memories.remember("O usuário gosta de jazz", owner="bruno", topic="lazer")
    pm.documents.add_bytes("ata.md", "# Ata\n\nO orçamento foi aprovado.".encode(),
                           owner="bruno", collection="atas")
    ids = {"memories": [m["id"] for m in pm.memories.list(owner="ana")["memories"]],
           "documents": [d["id"] for d in pm.documents.list(owner="ana")["documents"]],
           "chunks": [c["id"] for c in pm.documents.chunks(owner="ana")["chunks"]]}
    return pm, llm, ids


def snapshot(pm):
    """Everything ana has, as the operations return it (without the graph's generation time)."""
    results = [dispatch(pm, name, {"owner": "ana", **extra}) for name, extra in [
        ("memories.list", {}), ("documents.list", {}), ("collections.list", {}),
        ("chunks.list", {"limit": 500}), ("graph.data", {"include_documents": True,
                                                         "include_chunks": True})]]
    results[-1].pop("generated_at")
    return json.dumps(results, sort_keys=True)


def attack(ids):
    """bruno calls every operation, reading first, then writing, then deleting everything."""
    me = {"owner": "bruno"}
    reads = [
        ("memories.search", {**me, "query": MARK, "limit": 50}),
        ("memories.list", {**me, "limit": 500}),
        ("memories.list", {**me, "topic": "casa"}),
        ("documents.search", {**me, "query": MARK, "limit": 50}),
        ("documents.search", {**me, "query": MARK, "collection": "atas"}),
        ("documents.list", me),
        ("documents.list", {**me, "collection": "atas"}),
        ("collections.list", me),
        ("chunks.list", {**me, "limit": 500}),
        ("chunks.list", {**me, "collection": "atas"}),
        ("graph.data", {**me, "include_documents": True, "include_chunks": True}),
        ("graph.html", {**me, "include_chunks": True}),
        ("stats", me),
        *[("memories.get", {**me, "memory_id": i}) for i in ids["memories"]],
        *[("documents.get", {**me, "doc_id": i}) for i in ids["documents"]],
        *[("chunks.list", {**me, "doc_id": i}) for i in ids["documents"]],
        *[("chunks.get", {**me, "chunk_id": i}) for i in ids["chunks"]],
    ]
    writes = [
        ("memories.add", {**me, "messages": "eu toco violão"}),
        ("memories.remember", {**me, "text": "O usuário tem um cachorro", "topic": "casa"}),
        ("documents.add", {**me, "filename": "ata.md", "collection": "atas",
                           "content_base64": b64("# Ata\n\nNova versão.")}),
        ("documents.add_text", {**me, "title": "Notas", "text": "Lista de compras."}),
        *[("memories.update", {**me, "memory_id": i, "text": "trocado"}) for i in ids["memories"]],
        *[("memories.delete", {**me, "memory_id": i}) for i in ids["memories"]],
        *[("documents.remove", {**me, "doc_id": i}) for i in ids["documents"]],
        *[("chunks.delete", {**me, "chunk_id": i}) for i in ids["chunks"]],
        ("collections.delete", {**me, "name": "atas"}),
        ("collections.delete", {**me, "name": "geral"}),
        ("memories.delete_all", me),
    ]
    return reads + writes


def owners(value):
    """Every value under an "owner" key, anywhere in the result."""
    if isinstance(value, dict):
        found = [value["owner"]] if "owner" in value else []
        return found + [o for v in value.values() for o in owners(v)]
    if isinstance(value, list):
        return [o for v in value for o in owners(v)]
    return []


def check(pm, llm, ids, before, sequence, results):
    ana_ids = {i for group in ids.values() for i in group}
    for (name, params), result in zip(sequence, results, strict=True):
        text = json.dumps(result, ensure_ascii=False)
        assert MARK not in text, (name, params, text[:300])
        assert set(owners(result)) <= {"bruno"}, (name, params)
        targets = {params.get(k) for k in ("memory_id", "doc_id", "chunk_id")} & ana_ids
        if targets and name != "chunks.list":
            assert result.get("error", {}).get("code") == "not_found", (name, result)
        elif "error" not in result:
            assert not any(i in text for i in ana_ids), (name, params)
    assert all(MARK not in p for p in llm.prompts[before["prompts"]:]), "dados de ana no modelo"
    assert snapshot(pm) == before["ana"]
    assert dispatch(pm, "memories.list", {"owner": "bruno"})["total"] == 0


def test_every_operation_is_attacked():
    assert {name for name, _ in attack({"memories": ["m"], "documents": ["d"],
                                        "chunks": ["c"]})} == set(OPERATIONS)


TRANSPORTS = {
    "biblioteca": lambda mp, pm, seq: via_dispatch(pm, seq),
    "http": lambda mp, pm, seq: via_http(pm, seq),
    "cli": lambda mp, pm, seq: via_cli(mp, pm, seq),
    "mcp": lambda mp, pm, seq: via_mcp(pm, seq),
}


@pytest.mark.parametrize("transport", TRANSPORTS)
def test_one_owner_cannot_reach_another(transport, monkeypatch):
    if transport == "mcp" and not importlib.util.find_spec("mcp"):
        pytest.skip("extra mcp não instalado")
    pm, llm, ids = seeded()
    assert len(ids["memories"]) == 2 and len(ids["documents"]) == 2 and ids["chunks"]
    before = {"ana": snapshot(pm), "prompts": len(llm.prompts)}
    sequence = attack(ids)
    results = TRANSPORTS[transport](monkeypatch, pm, sequence)
    check(pm, llm, ids, before, sequence, results)


def minimal(name, ids):
    """The required parameters of an operation, aimed at ana's records, without the owner."""
    values = {"messages": "eu toco violão", "text": "x", "query": MARK, "title": "x",
              "name": "atas", "memory_id": ids["memories"][0], "doc_id": ids["documents"][0],
              "chunk_id": ids["chunks"][0]}
    if name == "documents.add":
        return {"filename": "ata.md", "content_base64": b64("# Ata\n\nx"), "collection": "atas"}
    return {k: values[k] for k in OPERATIONS[name].schema["required"] if k != "owner"}


@pytest.mark.parametrize("owner", [..., "", None, ["ana"], {"$ne": "x"}],
                         ids=["sem", "vazio", "nulo", "lista", "objeto"])
def test_owner_is_required(owner):
    """No operation runs without a valid owner: nothing like "all owners" exists."""
    pm, _, ids = seeded()
    before = snapshot(pm)
    for name in OPERATIONS:
        params = minimal(name, ids) | ({} if owner is ... else {"owner": owner})
        result = dispatch(pm, name, params)
        assert result.get("error", {}).get("code") == "invalid_input", (name, owner, result)
    assert snapshot(pm) == before


@pytest.mark.parametrize("owner", ["*", "%", ".*", "ANA", "ana ", "Ana"])
def test_owner_is_matched_literally(owner):
    """Wildcards, case and spaces never widen the owner."""
    pm, _, ids = seeded()
    before = snapshot(pm)
    for name in OPERATIONS:
        result = dispatch(pm, name, minimal(name, ids) | {"owner": owner})
        assert MARK not in json.dumps(result, ensure_ascii=False), (name, owner)
        assert set(owners(result)) <= {owner}, (name, owner)
    assert snapshot(pm) == before
