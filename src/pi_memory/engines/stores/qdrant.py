"""Qdrant: the default store. Local (embedded in a folder) or a server by URL.

Each point has a dense vector ("dense") and a sparse vector of its words ("terms") whose IDF Qdrant
computes itself (Modifier.IDF), so the hybrid search is native: both prefetched and fused with
DBSF (see search.py for why DBSF). The embedder used by each collection is kept in a vectorless
collection, `pi_memory_meta`, which works with any Qdrant version.
"""

from __future__ import annotations

import uuid
import zlib

from pi_memory import config
from pi_memory.engines._extras import require
from pi_memory.errors import EngineUnavailableError, StoreBusyError
from pi_memory.interfaces import Hit, Record

_META = "pi_memory_meta"
_DENSE = "dense"
_TERMS = "terms"
_ID = "_id"
_TEXT = "_text"
_NS = uuid.UUID("5d1f5c4e-3b0a-4c39-9a57-6e1b0c2f7a11")
_PAGE = 256
_K1 = 1.2   # same k1 as search.BM25Index


def _point_id(item_id: str) -> str:
    return str(uuid.uuid5(_NS, item_id))


class QdrantStore:
    native_hybrid = True

    def __init__(self, path: str | None = None, url: str | None = None,
                 api_key: str | None = None, timeout: float = config.TIMEOUT_S):
        qc = require("qdrant_client", "qdrant", "O banco Qdrant")
        self._m = require("qdrant_client.models", "qdrant", "O banco Qdrant")
        self.where_label = url or path or ":memory:"
        try:
            if url:
                self._client = qc.QdrantClient(url=url, api_key=api_key, timeout=int(timeout))
            else:
                self._client = qc.QdrantClient(path=path or config.DEFAULT_PATH)
        except RuntimeError as e:
            if "already accessed" in str(e):
                raise StoreBusyError(
                    f"A memória em '{path}' já está aberta por outro programa. Feche o outro "
                    "programa, use o servidor do pi-memory ou um Qdrant em modo servidor."
                ) from None
            raise
        self._server = bool(url)

    # ── helpers ──────────────────────────────────────────────────────────────────────────────
    def _filter(self, where: dict | None):
        m = self._m
        if not where:
            return None
        return m.Filter(must=[
            m.FieldCondition(key=key, match=m.MatchValue(value=value))
            for key, value in where.items()
        ])

    def _sparse(self, terms: dict[str, float], query: bool = False):
        """Documents: BM25 term-frequency saturation tf·(k1+1)/(tf+k1); Qdrant multiplies by the
        IDF (Modifier.IDF). Query: weight 1 per term. Same idea as the library's BM25. Raw counts
        gave 49/52 right pieces in the top 3; saturated, 50/52 (eval documents, 2026-11-04)."""
        counts: dict[int, float] = {}
        for term, tf in terms.items():
            weight = 1.0 if query else tf * (_K1 + 1) / (tf + _K1)
            index = zlib.crc32(term.encode("utf-8")) & 0x7FFFFFFF
            counts[index] = counts.get(index, 0.0) + weight
        return self._m.SparseVector(indices=list(counts), values=list(counts.values()))

    @staticmethod
    def _record(point, with_vector: bool = False) -> Record:
        payload = dict(point.payload or {})
        item_id = payload.pop(_ID, str(point.id))
        text = payload.pop(_TEXT, "")
        vector = None
        if with_vector and point.vector is not None:
            vector = point.vector.get(_DENSE) if isinstance(point.vector, dict) else point.vector
        return Record(item_id, text, payload, vector)

    def _call(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # network errors of a Qdrant server
            if type(e).__name__ in ("ResponseHandlingException", "ConnectError", "ConnectTimeout"):
                raise EngineUnavailableError(
                    f"o Qdrant não respondeu em {self.where_label} — ele está aberto?"
                ) from None
            raise

    # ── VectorStore ──────────────────────────────────────────────────────────────────────────
    def open_collection(self, name: str, dimension: int, meta: dict) -> dict:
        m = self._m
        if not self._call(self._client.collection_exists, _META):
            self._client.create_collection(_META, vectors_config={})
        stored = self._client.retrieve(_META, [_point_id(name)], with_payload=True)
        if stored and self._client.collection_exists(name):
            return dict(stored[0].payload or {})
        if not self._client.collection_exists(name):
            self._client.create_collection(
                name,
                vectors_config={_DENSE: m.VectorParams(size=dimension, distance=m.Distance.COSINE)},
                sparse_vectors_config={_TERMS: m.SparseVectorParams(modifier=m.Modifier.IDF)},
            )
            if self._server:  # payload indexes have no effect in local mode
                for field in ("owner", "doc_id", "topic"):
                    self._client.create_payload_index(name, field, m.PayloadSchemaType.KEYWORD)
        self.set_meta(name, meta)
        return dict(meta)

    def set_meta(self, name: str, meta: dict) -> None:
        self._client.upsert(_META, [self._m.PointStruct(id=_point_id(name), vector={},
                                                        payload=dict(meta))])

    def upsert(self, collection: str, records: list[Record]) -> None:
        m = self._m
        points = []
        for r in records:
            vector = {_DENSE: r.vector}
            if r.terms:
                vector[_TERMS] = self._sparse(r.terms)
            points.append(m.PointStruct(id=_point_id(r.id), vector=vector,
                                        payload={**r.payload, _ID: r.id, _TEXT: r.text}))
        if points:
            self._call(self._client.upsert, collection, points)

    def delete(self, collection: str, ids: list[str] | None = None,
               where: dict | None = None) -> int:
        m = self._m
        removed = 0
        if ids:
            found = self._client.retrieve(collection, [_point_id(i) for i in ids])
            if found:
                self._call(self._client.delete, collection,
                           points_selector=m.PointIdsList(points=[p.id for p in found]))
            removed += len(found)
        if where is not None:
            selector = self._filter(where) or m.Filter()
            removed += self._client.count(collection, count_filter=selector, exact=True).count
            self._call(self._client.delete, collection,
                       points_selector=m.FilterSelector(filter=selector))
        return removed

    def get(self, collection: str, ids: list[str]) -> list[Record]:
        if not ids:
            return []
        points = self._call(self._client.retrieve, collection, [_point_id(i) for i in ids],
                            with_payload=True)
        by_id = {r.id: r for r in (self._record(p) for p in points)}
        return [by_id[i] for i in ids if i in by_id]

    def scan(self, collection: str, where: dict, limit: int | None = None, offset: int = 0,
             with_vectors: bool = False) -> list[Record]:
        wanted = None if limit is None else offset + limit
        found: list[Record] = []
        next_page = None
        while True:
            points, next_page = self._call(
                self._client.scroll, collection, scroll_filter=self._filter(where),
                limit=_PAGE, offset=next_page, with_payload=True,
                with_vectors=[_DENSE] if with_vectors else False)
            found.extend(self._record(p, with_vectors) for p in points)
            if next_page is None or (wanted is not None and len(found) >= wanted):
                break
        return found[offset:wanted]

    def count(self, collection: str, where: dict) -> int:
        return self._call(self._client.count, collection, count_filter=self._filter(where),
                          exact=True).count

    def dense_search(self, collection: str, vector: list[float], where: dict,
                     limit: int) -> list[Hit]:
        result = self._call(self._client.query_points, collection, query=vector, using=_DENSE,
                            query_filter=self._filter(where), limit=limit, with_payload=True)
        return [Hit(self._record(p), p.score) for p in result.points]

    def hybrid_search(self, collection: str, vector: list[float], terms: dict[str, float],
                      where: dict, limit: int) -> list[Hit]:
        m = self._m
        flt = self._filter(where)
        if not terms:
            return self.dense_search(collection, vector, where, limit)
        result = self._call(
            self._client.query_points, collection,
            prefetch=[
                m.Prefetch(query=vector, using=_DENSE, filter=flt, limit=config.HYBRID_PREFETCH),
                m.Prefetch(query=self._sparse(terms, query=True), using=_TERMS, filter=flt,
                           limit=config.HYBRID_PREFETCH),
            ],
            query=m.FusionQuery(fusion=m.Fusion.DBSF), limit=limit, with_payload=True)
        return [Hit(self._record(p), p.score) for p in result.points]

    def close(self) -> None:
        self._client.close()
