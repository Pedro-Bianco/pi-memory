"""Language model in the OpenAI format (/chat/completions): OpenAI itself or any compatible
server through base_url (Ollama at http://localhost:11434/v1, LM Studio, OpenRouter, Groq, ...).
The model has no default: prices and names change, the developer chooses."""

from __future__ import annotations

from pi_memory import config
from pi_memory.engines import _openai_format as fmt
from pi_memory.engines._http import HttpEngine
from pi_memory.errors import EngineResponseError


class OpenAILLM:
    def __init__(self, model: str, api_key: str | None = None, base_url: str = fmt.OPENAI_URL,
                 timeout: float = config.TIMEOUT_S, temperature: float = 0, transport=None):
        self.model = model
        self.temperature = temperature
        self.base, key, self._headers = fmt.resolve(base_url, api_key)
        self._engine = fmt.engine_name(self.base)
        self._http = HttpEngine(self._engine, timeout, secret=key, key_hint=fmt.ENV,
                                transport=transport)

    def complete(self, prompt: str) -> str:
        data = self._http.post_json(f"{self.base}/chat/completions", {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
        }, self._headers)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise EngineResponseError(f"{self._engine} devolveu uma resposta sem texto.") from None
        if not isinstance(content, str):
            raise EngineResponseError(f"{self._engine} devolveu uma resposta sem texto.")
        return content
