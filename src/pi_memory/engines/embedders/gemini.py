"""Gemini embeddings through the Google AI Studio API (global endpoint, simple key). Vertex AI,
with a chosen region, is a possible future engine."""

from __future__ import annotations

from pi_memory import config
from pi_memory.engines._http import HttpEngine, resolve_key
from pi_memory.engines.embedders._common import checked

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"
ENV = "GEMINI_API_KEY"
_BATCH = 100   # the API limit per batchEmbedContents call


class GeminiEmbedder:
    def __init__(self, model: str = "gemini-embedding-001", api_key: str | None = None,
                 timeout: float = config.TIMEOUT_S, output_dimensionality: int | None = None,
                 transport=None):
        key = resolve_key(api_key, ENV, "A API do Gemini")
        self.model = model
        self.output_dimensionality = output_dimensionality
        suffix = f"@{output_dimensionality}" if output_dimensionality else ""
        self.name = f"gemini:{model}{suffix}"
        self._headers = {"x-goog-api-key": key}   # in a header, never in the URL (logs)
        self._http = HttpEngine("a API do Gemini", timeout, secret=key, key_hint=ENV,
                                transport=transport)
        self._dimension: int | None = None

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            self._dimension = len(self.embed_query("teste"))
        return self._dimension

    def _embed(self, texts: list[str], task: str) -> list[list[float]]:
        requests = []
        for text in texts:
            item = {"model": f"models/{self.model}", "content": {"parts": [{"text": text}]},
                    "taskType": task}
            if self.output_dimensionality:
                item["outputDimensionality"] = self.output_dimensionality
            requests.append(item)
        data = self._http.post_json(f"{GEMINI_URL}/models/{self.model}:batchEmbedContents",
                                    {"requests": requests}, self._headers)
        values = [e.get("values") for e in data.get("embeddings") or []]
        return checked(values, len(texts), "a API do Gemini")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH):
            vectors.extend(self._embed(texts[start:start + _BATCH], "RETRIEVAL_DOCUMENT"))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "RETRIEVAL_QUERY")[0]
