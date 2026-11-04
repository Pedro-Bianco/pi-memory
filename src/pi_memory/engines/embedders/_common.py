from __future__ import annotations

from pi_memory._util import unit
from pi_memory.errors import EngineResponseError


def checked(vectors, expected: int, engine: str) -> list[list[float]]:
    if not isinstance(vectors, list) or len(vectors) != expected:
        got = len(vectors) if isinstance(vectors, list) else 0
        raise EngineResponseError(f"{engine} devolveu {got} vetores para {expected} textos.")
    return [unit(v) for v in vectors]
