"""Long-term memory: add, update, delete, ignore and the safe fallbacks (scripted model)."""

import re

import pytest

from pi_memory import EngineUnavailableError, InvalidInputError, NotFoundError
from tests.fakes import ScriptedLLM, make_pm


def router(extraction="NULO", topics=None, decisions=()):
    """A handler answering by prompt kind; decisions are consumed in order."""
    queue = list(decisions)

    def handle(prompt: str) -> str:
        if prompt.startswith("Abaixo está um trecho de conversa"):
            return extraction
        if prompt.startswith("Classifique cada memória"):
            count = len(re.findall(r"^\d+\. ", prompt, re.MULTILINE))
            return topics or "\n".join(f"{i}. outros" for i in range(1, count + 1))
        if prompt.startswith("Você é um gerenciador de memória"):
            reply = queue.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply
        raise AssertionError(prompt[:200])

    return handle


def pm_with(**kwargs):
    llm = ScriptedLLM(handler=router(**kwargs))
    return make_pm(llm=llm), llm


def test_two_new_facts_are_added_with_topics():
    pm, llm = pm_with(extraction="FATO: O nome do usuário é Ana Exemplo\n"
                                 "FATO: O usuário mora em Cidade Exemplo",
                      topics="1. perfil\n2. casa", decisions=["ADD"])
    result = pm.memories.add("meu nome é Ana Exemplo e moro em Cidade Exemplo", owner="ana")
    decisions = result["decisions"]
    assert [d["event"] for d in decisions] == ["add", "add"]
    assert [d["topic"] for d in decisions] == ["perfil", "casa"]
    assert all(d["memory_id"] and d["previous_text"] is None and d["reason"] is None
               for d in decisions)
    assert pm.memories.list(owner="ana")["total"] == 2


def test_move_replaces_old_city():
    pm, _ = pm_with(extraction="FATO: O usuário mora em Vila Exemplo", topics="1. casa",
                    decisions=["UPDATE 1"])
    old = pm.memories.remember("O usuário mora em Cidade Exemplo", owner="ana", topic="casa")
    decision = pm.memories.add("me mudei para Vila Exemplo", owner="ana")["decisions"][0]
    assert decision["event"] == "update"
    assert decision["memory_id"] == old["id"]
    assert decision["previous_text"] == "O usuário mora em Cidade Exemplo"
    texts = [m["text"] for m in pm.memories.list(owner="ana")["memories"]]
    assert texts == ["O usuário mora em Vila Exemplo"]
    assert pm.memories.get(old["id"], owner="ana")["updated_at"] >= old["updated_at"]


def test_forget_deletes():
    pm, _ = pm_with(extraction="DEIXOU: Não é verdade que o usuário gosta de café",
                    decisions=["DELETE 1"])
    old = pm.memories.remember("O usuário gosta de café", owner="ana")
    decision = pm.memories.add("esquece isso do café, não é verdade", owner="ana")["decisions"][0]
    assert decision["event"] == "delete"
    assert decision["memory_id"] == old["id"]
    assert decision["previous_text"] == "O usuário gosta de café"
    assert pm.memories.list(owner="ana")["total"] == 0


def test_repeated_fact_is_ignored_by_the_model():
    pm, _ = pm_with(extraction="FATO: O usuário é engenheiro", decisions=["DUPLICATE"])
    pm.memories.remember("O usuário trabalha como engenheiro", owner="ana")
    decision = pm.memories.add("sou engenheira", owner="ana")["decisions"][0]
    assert decision["event"] == "none"
    assert pm.memories.list(owner="ana")["total"] == 1


def test_identical_fact_is_ignored_without_asking_the_model():
    pm, llm = pm_with(extraction="FATO: O usuário trabalha como engenheiro.")
    pm.memories.remember("o usuário trabalha como Engenheiro", owner="ana")
    decision = pm.memories.add("sou engenheira", owner="ana")["decisions"][0]
    assert decision["event"] == "none"
    assert not any(p.startswith("Você é um gerenciador") for p in llm.prompts)


def test_greetings_create_nothing():
    pm, llm = pm_with(extraction="NULO")
    assert pm.memories.add("oi, tudo bem?", owner="ana") == {"decisions": []}
    assert len(llm.prompts) == 1


def test_stopped_being_true_without_matching_memory_stores_nothing():
    pm, _ = pm_with(extraction="DEIXOU: O usuário vendeu a moto")
    decision = pm.memories.add("vendi minha moto", owner="ana")["decisions"][0]
    assert decision["event"] == "none"
    assert pm.memories.list(owner="ana")["total"] == 0


def test_owners_are_isolated():
    pm, _ = pm_with()
    a = pm.memories.remember("O usuário gosta de xadrez", owner="ana")
    pm.memories.remember("O usuário gosta de xadrez", owner="bruno")
    results = pm.memories.search("xadrez", owner="ana")["results"]
    assert [r["memory"]["owner"] for r in results] == ["ana"]
    assert pm.memories.list(owner="bruno")["total"] == 1
    with pytest.raises(NotFoundError):
        pm.memories.get(a["id"], owner="bruno")
    with pytest.raises(NotFoundError):
        pm.memories.delete(a["id"], owner="bruno")


def test_manual_crud_is_immediate():
    pm, _ = pm_with()
    m = pm.memories.remember("O usuário prefere reuniões pela manhã", owner="ana",
                             topic="trabalho", metadata={"origem": "manual"})
    assert m["topic"] == "trabalho" and m["metadata"] == {"origem": "manual"}
    first = pm.memories.search("quando prefere reunião?", owner="ana")["results"][0]
    assert first["kind"] == "memory" and first["id"] == m["id"] and first["memory"] == m
    changed = pm.memories.update(m["id"], owner="ana", text="O usuário prefere reuniões à tarde")
    found = pm.memories.search("reuniões tarde", owner="ana")["results"][0]
    assert found["text"] == changed["text"]
    assert pm.memories.list(owner="ana", topic="trabalho")["total"] == 1
    assert pm.memories.list(owner="ana", topic="lazer")["total"] == 0
    filtered = pm.memories.search("reuniões", owner="ana", filters={"metadata.origem": "x"})
    assert filtered["results"] == []
    assert pm.memories.delete(m["id"], owner="ana") == {"deleted": 1}
    pm.memories.remember("um", owner="ana")
    pm.memories.remember("dois", owner="ana")
    assert pm.memories.delete_all(owner="ana") == {"deleted": 2}
    assert pm.memories.search("um", owner="ana") == {"results": []}


@pytest.mark.parametrize("reply, reason", [
    ("hmm, não sei", "fallback_unclear"),
    ("UPDATE 9", "fallback_unclear"),
    (EngineUnavailableError("fora do ar"), "fallback_engine_error"),
])
def test_unclear_decision_keeps_both(reply, reason):
    pm, _ = pm_with(extraction="FATO: O usuário mora em Vila Exemplo", decisions=[reply])
    pm.memories.remember("O usuário mora em Cidade Exemplo", owner="ana")
    decision = pm.memories.add("moro em Vila Exemplo", owner="ana")["decisions"][0]
    assert decision["event"] == "add"
    assert decision["reason"] == reason
    assert pm.memories.list(owner="ana")["total"] == 2


def test_extraction_engine_error_writes_nothing():
    llm = ScriptedLLM(replies=[EngineUnavailableError("o Ollama não respondeu")])
    pm = make_pm(llm=llm)
    with pytest.raises(EngineUnavailableError):
        pm.memories.add("me chamo Ana Exemplo", owner="ana")
    assert pm.memories.list(owner="ana")["total"] == 0


def test_invalid_inputs_are_explained_in_portuguese():
    pm, _ = pm_with()
    with pytest.raises(InvalidInputError, match="dono"):
        pm.memories.add("oi", owner="")
    with pytest.raises(InvalidInputError, match="role"):
        pm.memories.add([{"role": "sistema", "content": "x"}], owner="ana")
    with pytest.raises(InvalidInputError, match="(?i)assunto"):
        pm.memories.remember("x", owner="ana", topic="astronomia")
    with pytest.raises(InvalidInputError, match="limit"):
        pm.memories.search("x", owner="ana", limit=0)


def test_same_timestamp_keeps_order_and_paging_stable(monkeypatch):
    """Windows' clock moves in ~15 ms steps: memories saved together share updated_at. The id
    breaks the tie, so the order never changes between calls and offset paging covers each
    memory exactly once (this test also runs on Qdrant and Chroma)."""
    monkeypatch.setattr("pi_memory.memories.now_iso", lambda: "2026-01-01T00:00:00.000000Z")
    pm, _ = pm_with()
    for i in range(12):
        pm.memories.remember(f"O usuário guardou o objeto número {i}", owner="ana", topic="casa")
    first = [m["id"] for m in pm.memories.list(owner="ana")["memories"]]
    pm.memories.remember("O usuário de outro dono", owner="bruno", topic="casa")
    assert [m["id"] for m in pm.memories.list(owner="ana")["memories"]] == first
    pages = [m["id"] for offset in range(0, 12, 5)
             for m in pm.memories.list(owner="ana", limit=5, offset=offset)["memories"]]
    assert pages == first and len(set(pages)) == 12
