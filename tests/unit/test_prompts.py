from pi_memory.interfaces import ExtractedFact
from pi_memory.prompts.portuguese import PortuguesePrompts

P = PortuguesePrompts()
TOPICS = ("trabalho", "família", "saúde", "outros")


def test_extraction_prompt_has_roles_and_truncates_assistant():
    prompt = P.extraction([{"role": "assistant", "content": "x" * 1000},
                           {"role": "user", "content": "sim, desde 2018"}])
    assert "ASSISTENTE: " + "x" * 400 + "…" in prompt
    assert prompt.rstrip().endswith("USUÁRIO: sim, desde 2018\nSaída:")


def test_parse_extraction_tags_bullets_and_noise():
    raw = """Saída:
- FATO: O usuário mora em Cidade Exemplo
2) DEIXOU: O usuário vendeu a moto
**FATO:** O usuário tem uma gata
FATO: O nome do usuário não foi informado
NULO
O usuário gosta de café"""
    facts = P.parse_extraction(raw)
    assert facts == [
        ExtractedFact("O usuário mora em Cidade Exemplo", False),
        ExtractedFact("O usuário vendeu a moto", True),
        ExtractedFact("O usuário tem uma gata", False),
        ExtractedFact("O usuário gosta de café", False),
    ]


def test_parse_extraction_nothing():
    assert P.parse_extraction("NULO") == []
    assert P.parse_extraction("") == []


def test_parse_topics_unknown_and_missing_lines_fall_back():
    raw = "1. Trabalho\n2. familia\n3. astronomia"
    assert P.parse_topics(raw, 4, TOPICS) == ["trabalho", "família", "outros", "outros"]


def test_parse_decision_tolerant_shapes():
    assert P.parse_decision("UPDATE 2", 3) == ("UPDATE", 1)
    assert P.parse_decision('```json {"action": "DELETE", "n": 1}```', 3) == ("DELETE", 0)
    assert P.parse_decision("Resposta: DUPLICATE", 2) == ("DUPLICATE", None)
    assert P.parse_decision("add", 2) == ("ADD", None)
    assert P.parse_decision("UPDATE", 1) == ("UPDATE", 0)


def test_parse_decision_unclear_is_none():
    assert P.parse_decision("não sei", 2) is None
    assert P.parse_decision("UPDATE 7", 3) is None
    assert P.parse_decision("DELETE", 2) is None


def test_decision_prompt_numbers_candidates():
    prompt = P.decision(ExtractedFact("O usuário se mudou"), ["a", "b"])
    assert '[1] "a"\n[2] "b"' in prompt and '"O usuário se mudou"' in prompt
