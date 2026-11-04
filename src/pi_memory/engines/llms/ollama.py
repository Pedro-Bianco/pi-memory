"""Ollama: the default language model, running locally."""

from __future__ import annotations

from pi_memory import config
from pi_memory.engines._http import HttpEngine
from pi_memory.errors import EngineResponseError


class OllamaLLM:
    def __init__(self, model: str = config.DEFAULT_LLM_MODEL, host: str = config.OLLAMA_HOST,
                 timeout: float = config.TIMEOUT_S, options: dict | None = None, transport=None):
        self.model = model
        self.host = host.rstrip("/")
        # temperature 0: extraction and decisions must be repeatable.
        self.options = {"temperature": 0, **(options or {})}
        self._http = HttpEngine("o Ollama", timeout, transport=transport)

    def complete(self, prompt: str) -> str:
        try:
            data = self._http.post_json(f"{self.host}/api/chat", {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "think": False,
                "options": self.options,
            })
        except EngineResponseError as e:
            if "not found" in e.message.lower():
                raise EngineResponseError(
                    f"O modelo '{self.model}' não está no Ollama. "
                    f"Baixe com: ollama pull {self.model}"
                ) from None
            raise
        content = (data.get("message") or {}).get("content")
        if not isinstance(content, str):
            raise EngineResponseError("o Ollama devolveu uma resposta sem texto.")
        return content
