"""FastEmbed: the default embedder. Runs locally (ONNX on the CPU); the model is downloaded once
and then works without internet."""

from __future__ import annotations

import warnings

from pi_memory import config
from pi_memory._util import unit
from pi_memory.engines._extras import require


class FastEmbedEmbedder:
    def __init__(self, model: str = config.DEFAULT_EMBEDDING_MODEL, cache_dir: str | None = None,
                 batch_size: int = config.EMBED_BATCH):
        fastembed = require("fastembed", "fastembed", "O embedding FastEmbed")
        self.name = f"fastembed:{model}"
        self.model = model
        self.batch_size = batch_size
        # e5 models were trained with these prefixes; without them retrieval gets worse.
        self._e5 = "e5" in model.lower()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            self._model = fastembed.TextEmbedding(model_name=model, cache_dir=cache_dir)
        self._dimension: int | None = None

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            self._dimension = len(self.embed_query("teste"))
        return self._dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        prefixed = [f"passage: {t}" for t in texts] if self._e5 else list(texts)
        return [unit(v) for v in self._model.embed(prefixed, batch_size=self.batch_size)]

    def embed_query(self, text: str) -> list[float]:
        prefixed = f"query: {text}" if self._e5 else text
        return unit(next(iter(self._model.embed([prefixed]))))
