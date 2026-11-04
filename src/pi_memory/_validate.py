"""Input checks of the Python API, with messages in Portuguese. The CLI, HTTP and MCP reach the
same checks because they call the same methods."""

from __future__ import annotations

from collections.abc import Sequence

from pi_memory import config
from pi_memory.errors import InvalidInputError

_SCALARS = (str, int, float, bool)


def owner(value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidInputError("Informe o dono (owner): um texto não vazio, ex. 'ana'.")
    if len(value) > 200:
        raise InvalidInputError("O dono (owner) pode ter no máximo 200 caracteres.")
    return value


def text(value, field: str = "text") -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidInputError(f"O campo '{field}' precisa ser um texto não vazio.")
    if len(value) > config.MAX_MEMORY_CHARS:
        raise InvalidInputError(
            f"O campo '{field}' pode ter no máximo {config.MAX_MEMORY_CHARS} caracteres.")
    return value.strip()


def query(value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidInputError("A busca (query) precisa ser um texto não vazio.")
    return value


def limit(value, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise InvalidInputError(
            f"O limite (limit) precisa ser um número inteiro de 1 a {maximum}.")
    return value


def offset(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidInputError("O deslocamento (offset) precisa ser um número inteiro ≥ 0.")
    return value


def mapping(value, field: str) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(
            isinstance(k, str) and isinstance(v, _SCALARS) for k, v in value.items()):
        raise InvalidInputError(
            f"O campo '{field}' precisa ser um objeto com valores simples "
            "(texto, número, sim/não).")
    return dict(value)


def topic(value, allowed: Sequence[str]) -> str:
    if value not in allowed:
        raise InvalidInputError(
            f"Assunto '{value}' não está na lista configurada: {', '.join(allowed)}.")
    return value


def messages(value) -> list[dict]:
    if isinstance(value, str):
        return [{"role": "user", "content": text(value, "messages")}]
    if not isinstance(value, list) or not value:
        raise InvalidInputError(
            "As mensagens (messages) precisam ser um texto ou uma lista de "
            "{'role': 'user' | 'assistant', 'content': texto}.")
    checked = []
    for item in value:
        if not isinstance(item, dict) or item.get("role") not in ("user", "assistant"):
            raise InvalidInputError("Cada mensagem precisa ter role 'user' ou 'assistant'.")
        if not isinstance(item.get("content"), str):
            raise InvalidInputError("Cada mensagem precisa ter 'content' em texto.")
        checked.append({"role": item["role"], "content": item["content"]})
    return checked
