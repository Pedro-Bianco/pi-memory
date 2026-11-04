"""Language model through the Anthropic API (/v1/messages). Language model only: Anthropic offers no
embedding model. The model has no default: the developer chooses."""

from __future__ import annotations

from pi_memory import config
from pi_memory.engines._http import HttpEngine, resolve_key
from pi_memory.errors import EngineResponseError

ANTHROPIC_URL = "https://api.anthropic.com"
ENV = "ANTHROPIC_API_KEY"


class AnthropicLLM:
    def __init__(self, model: str, api_key: str | None = None, base_url: str = ANTHROPIC_URL,
                 timeout: float = config.TIMEOUT_S, max_tokens: int = 1024,
                 temperature: float = 0, transport=None):
        key = resolve_key(api_key, ENV, "A API da Anthropic")
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.base = base_url.rstrip("/")
        self._headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        self._http = HttpEngine("a API da Anthropic", timeout, secret=key, key_hint=ENV,
                                transport=transport)

    def complete(self, prompt: str) -> str:
        data = self._http.post_json(f"{self.base}/v1/messages", {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }, self._headers)
        blocks = data.get("content")
        if not isinstance(blocks, list):
            raise EngineResponseError("a API da Anthropic devolveu uma resposta sem texto.")
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
