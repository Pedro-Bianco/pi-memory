"""Any function the user provides as the language model: text in, text out."""

from __future__ import annotations

from collections.abc import Callable

from pi_memory.errors import EngineResponseError, PiMemoryError


class FunctionLLM:
    def __init__(self, fn: Callable[[str], str]):
        self.fn = fn

    def complete(self, prompt: str) -> str:
        try:
            result = self.fn(prompt)
        except PiMemoryError:
            raise
        except Exception as e:
            raise EngineResponseError(f"A função de linguagem falhou: {e}") from None
        if not isinstance(result, str):
            raise EngineResponseError(
                f"A função de linguagem devolveu {type(result).__name__}; ela deve devolver texto."
            )
        return result
