"""Embeddings served by the local Ollama (/api/embed)."""

from __future__ import annotations

from pi_memory import config
from pi_memory.engines._http import HttpEngine
from pi_memory.engines.embedders._common import checked

# Models trained with task prefixes; without them retrieval gets worse (model cards).
_PREFIXES = {
    "nomic-embed-text": ("search_query: ", "search_document: "),
}


class OllamaEmbedder:
    def __init__(self, model: str = "nomic-embed-text", host: str = config.OLLAMA_HOST,
                 timeout: float = config.TIMEOUT_S, transport=None):
        self.model = model
        self.name = f"ollama:{model}"
        self.host = host.rstrip("/")
        self._query_prefix, self._doc_prefix = _PREFIXES.get(model.split(":")[0], ("", ""))
        self._http = HttpEngine("o Ollama", timeout, transport=transport)
        self._dimension: int | None = None

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            self._dimension = len(self.embed_query("teste"))
        return self._dimension

    def _embed(self, texts: list[str]) -> list[list[float]]:
        data = self._http.post_json(f"{self.host}/api/embed",
                                    {"model": self.model, "input": texts})
        return checked(data.get("embeddings"), len(texts), "o Ollama")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed([self._doc_prefix + t for t in texts]) if texts else []

    def embed_query(self, text: str) -> list[float]:
        return self._embed([self._query_prefix + text])[0]
