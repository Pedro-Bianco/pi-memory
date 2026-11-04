"""Gemini through the Google AI Studio API (generateContent). The model has no default: on
2026-11-04 gemini-2.5-flash, available a few months before, was already refused to new users."""

from __future__ import annotations

from pi_memory import config
from pi_memory.engines._http import HttpEngine, resolve_key
from pi_memory.engines.embedders.gemini import ENV, GEMINI_URL
from pi_memory.errors import EngineResponseError


class GeminiLLM:
    def __init__(self, model: str, api_key: str | None = None,
                 timeout: float = config.TIMEOUT_S, temperature: float = 0, transport=None):
        key = resolve_key(api_key, ENV, "A API do Gemini")
        self.model = model
        self.temperature = temperature
        self._headers = {"x-goog-api-key": key}   # in a header, never in the URL (logs)
        self._http = HttpEngine("a API do Gemini", timeout, secret=key, key_hint=ENV,
                                transport=transport)

    def complete(self, prompt: str) -> str:
        data = self._http.post_json(f"{GEMINI_URL}/models/{self.model}:generateContent", {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": self.temperature},
        }, self._headers)
        blocked = (data.get("promptFeedback") or {}).get("blockReason")
        if blocked:
            raise EngineResponseError(f"a API do Gemini bloqueou o pedido ({blocked}).")
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError):
            reason = ((data.get("candidates") or [{}])[0] or {}).get("finishReason", "sem texto")
            raise EngineResponseError(f"a API do Gemini devolveu uma resposta vazia ({reason}).") \
                from None
        return "".join(p.get("text", "") for p in parts if not p.get("thought"))
