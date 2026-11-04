"""Embeddings in the OpenAI format (/embeddings): OpenAI itself or any compatible server through
base_url (Ollama at http://localhost:11434/v1, LM Studio, ...)."""

from __future__ import annotations

from pi_memory import config
from pi_memory.engines import _openai_format as fmt
from pi_memory.engines._http import HttpEngine
from pi_memory.engines.embedders._common import checked


class OpenAIEmbedder:
    def __init__(self, model: str, api_key: str | None = None, base_url: str = fmt.OPENAI_URL,
                 timeout: float = config.TIMEOUT_S, batch_size: int = 64, transport=None):
        self.model = model
        self.base, key, self._headers = fmt.resolve(base_url, api_key)
        local = "" if self.base == fmt.OPENAI_URL else f"{self.base}:"
        self.name = f"openai:{local}{model}"
        self.batch_size = batch_size
        self._engine = fmt.engine_name(self.base)
        self._http = HttpEngine(self._engine, timeout, secret=key, key_hint=fmt.ENV,
                                transport=transport)
        self._dimension: int | None = None

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            self._dimension = len(self.embed_query("teste"))
        return self._dimension

    def _embed(self, texts: list[str]) -> list[list[float]]:
        data = self._http.post_json(f"{self.base}/embeddings",
                                    {"model": self.model, "input": texts}, self._headers)
        items = sorted(data.get("data") or [], key=lambda item: item.get("index", 0))
        return checked([item.get("embedding") for item in items], len(texts), self._engine)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            vectors.extend(self._embed(texts[start:start + self.batch_size]))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]
