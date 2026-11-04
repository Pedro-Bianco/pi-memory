"""Default prompts, in Brazilian Portuguese: extraction, topic and decision.

They come from the original project, where they were measured; every change here must be checked
with eval/run.py --suite memory before and after. Example names are clearly
fictitious so the model never copies a real-looking fact. Parsers are tolerant: they look for the
word, not for JSON — requiring a JSON key once made every decision fall into ADD (measured 0/3).
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from pi_memory import config
from pi_memory._util import plain
from pi_memory.interfaces import ExtractedFact

_ASSISTANT_CHARS = 400   # long assistant answers would eat the extractor's window

EXTRACTION = """\
Abaixo está um trecho de conversa entre o USUÁRIO e o ASSISTENTE.
Extraia o que o USUÁRIO afirmou ou confirmou sobre si mesmo. Use as falas do ASSISTENTE só como
contexto (para entender um "sim" ou uma resposta curta); nunca extraia o que só o assistente disse.

Escreva um item por linha, em português, como frase completa sobre "o usuário", começando com:
FATO: fatos sobre o usuário (nome, como quer ser chamado, preferências, trabalho, cidade, família,
animais, projetos, hobbies, rotina, datas)
DEIXOU: algo sobre o usuário que deixou de ser verdade (vendeu, se mudou, saiu, não tem mais) ou
que o usuário pediu para esquecer por não ser verdade

Ignore pedidos e comandos (abrir programas, música, pesquisas, lembretes, perguntas gerais): não
são fatos sobre o usuário. O conteúdo de documentos e pesquisas também não é fato sobre o usuário.
Nunca escreva sobre ausência de informação. Se não houver nada, escreva NULO.

Exemplos:
Conversa:
USUÁRIO: me chamo Fulano Exemplo e sou engenheiro de dados
Saída:
FATO: O nome do usuário é Fulano Exemplo
FATO: O usuário é engenheiro de dados

Conversa:
ASSISTENTE: Você ainda mora em Cidade Exemplo?
USUÁRIO: sim, desde 2018
Saída:
FATO: O usuário mora em Cidade Exemplo desde 2018

Conversa:
USUÁRIO: vendi minha moto semana passada
Saída:
DEIXOU: O usuário vendeu a moto e não tem mais moto

Conversa:
USUÁRIO: esquece isso de eu gostar de jazz, não é verdade
Saída:
DEIXOU: Não é verdade que o usuário gosta de jazz

Conversa:
USUÁRIO: oi, tudo bem? abre a previsão do tempo
Saída:
NULO

Conversa:
{chat}
Saída:
"""

TOPICS = """\
Classifique cada memória sobre o usuário em UM assunto desta lista: {topics}.
Responda uma linha por memória, no formato: número. assunto

{items}"""

DECISION = """\
Você é um gerenciador de memória sobre o usuário. Compare o NOVO FATO com as memórias existentes.

Memórias existentes:
{memories}

Novo fato: "{new_fact}"

Responda com UMA linha:
ADD          → o novo fato é complementar ou de outro assunto (todas as memórias continuam valendo).
DUPLICATE    → o novo fato já está numa das memórias, mesmo com outras palavras.
UPDATE n     → o novo fato substitui a memória [n]: mesmo assunto, valor novo.
DELETE n     → a memória [n] deixou de ser verdade e o novo fato só diz isso, sem valor novo.

Exemplos:
[1] "O usuário mora em Cidade Exemplo" + "O usuário se mudou para Vila Exemplo" → UPDATE 1
[1] "O usuário tem um carro" + "O usuário vendeu o carro" → DELETE 1
[1] "O usuário é professor" + "O usuário dá aulas de história" → UPDATE 1
[1] "O usuário gosta de surfar" + "O usuário curte surfe" → DUPLICATE
[1] "O usuário tem uma gata chamada Mel" + "O usuário trabalha como enfermeiro" → ADD

Na dúvida, responda ADD — é melhor guardar duas memórias parecidas do que apagar uma válida.

Resposta:"""

_TAGGED = re.compile(r"^(FATO|DEIXOU|PERFIL)\s*[:\-–]\s*(.+)$", re.IGNORECASE)
_BULLET = re.compile(r"^\s*(?:[-*•]+|\d+[.)])\s*")

# Small models slip and store "O nome do usuário não foi informado" as a fact; a memory of absence
# is later recalled and the assistant claims not to know what it may already know.
_ABSENCE = (
    "nao foi fornecid", "nao informou", "nao foi informad", "nao ha informac", "nao menciona",
    "nao especificad", "desconhecid", "nao sabemos", "nao foi dito", "nao consta",
    "sem informac", "nao revelou",
)
_NOISE = ("nulo", "saida", "conversa", "nenhum", "nada")


def _is_absence(fact: str) -> bool:
    low = plain(fact)
    return any(marker in low for marker in _ABSENCE)


class PortuguesePrompts:
    def extraction(self, conversation: list[dict]) -> str:
        lines = []
        for message in conversation:
            content = " ".join(str(message.get("content", "")).split())
            if message.get("role") == "assistant":
                if len(content) > _ASSISTANT_CHARS:
                    content = content[:_ASSISTANT_CHARS] + "…"
                lines.append(f"ASSISTENTE: {content}")
            else:
                lines.append(f"USUÁRIO: {content}")
        return EXTRACTION.format(chat="\n".join(lines))

    def parse_extraction(self, raw: str) -> list[ExtractedFact]:
        facts: list[ExtractedFact] = []
        for line in (raw or "").splitlines():
            line = _BULLET.sub("", line.replace("**", "").strip().strip("*`")).strip()
            if not line or line.endswith(":"):
                continue
            tagged = _TAGGED.match(line)
            if tagged:
                tag, text = tagged.group(1).upper(), tagged.group(2).strip()
            else:
                tag, text = "FATO", line
            text = text.strip(" \"'")
            if not text or plain(text).strip(" .") in _NOISE or _is_absence(text):
                continue
            facts.append(ExtractedFact(text, stopped_being_true=(tag == "DEIXOU")))
        return facts

    def topics(self, facts: list[str], topics: Sequence[str]) -> str:
        items = "\n".join(f"{i}. {text}" for i, text in enumerate(facts, 1))
        return TOPICS.format(topics=", ".join(topics), items=items)

    def parse_topics(self, raw: str, count: int, topics: Sequence[str]) -> list[str]:
        by_plain = {plain(t): t for t in topics}
        fallback = config.FALLBACK_TOPIC if config.FALLBACK_TOPIC in topics else topics[-1]
        found: dict[int, str] = {}
        for match in re.finditer(r"^\s*(\d+)\s*[.)\-:]\s*(.+?)\s*$", raw or "", re.MULTILINE):
            key = plain(match.group(2)).strip(" .*`\"'")
            found[int(match.group(1))] = by_plain.get(key, fallback)
        return [found.get(i, fallback) for i in range(1, count + 1)]

    def decision(self, fact: ExtractedFact, candidates: list[str]) -> str:
        memories = "\n".join(f'[{i}] "{text}"' for i, text in enumerate(candidates, 1))
        return DECISION.format(memories=memories, new_fact=fact.text)

    def parse_decision(self, raw: str, candidate_count: int) -> tuple[str, int | None] | None:
        text = (raw or "").upper()
        word = re.search(r"\b(UPDATE|DELETE|DUPLICATE|ADD)\b", text)
        if not word:
            return None
        action = word.group(1)
        if action in ("ADD", "DUPLICATE"):
            return action, None
        number = re.search(r"\b(\d+)\b", text[word.end():]) or re.search(r"\[(\d+)\]", text)
        if number:
            index = int(number.group(1)) - 1
        else:
            index = 0 if candidate_count == 1 else -1
        if not 0 <= index < candidate_count:
            return None          # which memory? unclear: never delete or replace by guess
        return action, index
