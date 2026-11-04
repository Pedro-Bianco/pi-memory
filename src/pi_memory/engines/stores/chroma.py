"""Chroma: local (a folder) or a server. No native hybrid search: the library adds the exact-word
part (BM25) and the fusion, with the same tokenization as every other store.

Chroma metadata is flat (text, number, sim/não): the nested payload["metadata"] travels as
"metadata.<key>" fields and is rebuilt on the way back. The embedder record of the collection
lives in the collection's own metadata.
"""

from __future__ import annotations

import warnings

from pi_memory.engines._extras import require
from pi_memory.interfaces import Hit, Record

_NESTED = "metadata"
_PAGE = 500   # records per get(): see _pages
# Chroma 1.5.x bug: get(include=["embeddings"]) sometimes fails for good with "Error creating hnsw
# segment reader: Nothing found on disk" (reproduced with Chroma alone: 4 of 200 runs with a new
# client per run in one process; 0 of 60 with one client; Chroma 1.5.9, Windows, 2026-11-10).
# Retrying does not help. Only the graph reads vectors back: it then gets the records without
# vectors (no "similar" links) and a warning, instead of failing.
_VECTORS_MISSING = "Nothing found on disk"


def _flatten(payload: dict) -> dict:
    flat = {}
    for key, value in payload.items():
        if key == _NESTED and isinstance(value, dict):
            flat.update({f"{_NESTED}.{k}": v for k, v in value.items() if v is not None})
        elif value is not None:
            flat[key] = value
    return flat


def _unflatten(flat: dict | None) -> dict:
    payload: dict = {_NESTED: {}}
    for key, value in (flat or {}).items():
        if key.startswith(f"{_NESTED}."):
            payload[_NESTED][key[len(_NESTED) + 1:]] = value
        else:
            payload[key] = value
    return payload


def _where(where: dict | None):
    conditions = [{key: {"$eq": value}} for key, value in (where or {}).items()]
    if not conditions:
        return None
    return conditions[0] if len(conditions) == 1 else {"$and": conditions}


class ChromaStore:
    native_hybrid = False

    def __init__(self, path: str | None = None, host: str | None = None, port: int = 8000):
        chromadb = require("chromadb", "chroma", "O banco Chroma")
        if host:
            self._client = chromadb.HttpClient(host=host, port=port)
        elif path:
            self._client = chromadb.PersistentClient(path=str(path))
        else:
            self._client = chromadb.EphemeralClient()
        self._collections: dict = {}

    def _col(self, name: str):
        if name not in self._collections:
            self._collections[name] = self._client.get_collection(name, embedding_function=None)
        return self._collections[name]

    @staticmethod
    def _records(result: dict, with_vectors: bool = False) -> list[Record]:
        embeddings = result.get("embeddings") if with_vectors else None
        records = []
        for i, item_id in enumerate(result["ids"]):
            vector = [float(v) for v in embeddings[i]] if embeddings is not None else None
            records.append(Record(item_id, (result.get("documents") or [""] * (i + 1))[i] or "",
                                  _unflatten((result.get("metadatas") or [None] * (i + 1))[i]),
                                  vector))
        return records

    # ── VectorStore ──────────────────────────────────────────────────────────────────────────
    def open_collection(self, name: str, dimension: int, meta: dict) -> dict:
        try:
            return dict(self._col(name).metadata or {})
        except Exception:   # not found: the error type changed between Chroma versions
            self._collections[name] = self._client.get_or_create_collection(
                name, metadata=dict(meta) or None, embedding_function=None,
                configuration={"hnsw": {"space": "cosine"}})
            return dict(meta)

    def set_meta(self, name: str, meta: dict) -> None:
        self._col(name).modify(metadata=dict(meta))

    def upsert(self, collection: str, records: list[Record]) -> None:
        if records:
            self._col(collection).upsert(
                ids=[r.id for r in records], embeddings=[r.vector for r in records],
                documents=[r.text for r in records],
                metadatas=[_flatten(r.payload) or None for r in records])

    def _pages(self, col, where: dict | None, include: list[str], offset: int = 0,
               limit: int | None = None) -> dict:
        """Reads in pages: one get() over a whole large collection fails with "too many SQL
        variables" (measured with 10 000 records, Chroma 1.5.9, 2026-11-04)."""
        merged: dict = {"ids": [], "documents": [], "metadatas": [], "embeddings": []}
        while limit is None or len(merged["ids"]) < limit:
            size = _PAGE if limit is None else min(_PAGE, limit - len(merged["ids"]))
            page = col.get(where=_where(where), limit=size, offset=offset, include=include)
            for key in merged:
                if page.get(key) is not None:
                    merged[key].extend(page[key])
            offset += len(page["ids"])
            if len(page["ids"]) < size:
                break
        return {k: (v if v or k == "ids" else None) for k, v in merged.items()}

    def _by_ids(self, col, ids: list[str], include: list[str]) -> dict:
        merged: dict = {"ids": [], "documents": [], "metadatas": []}
        for start in range(0, len(ids), _PAGE):
            page = col.get(ids=ids[start:start + _PAGE], include=include)
            for key in merged:
                merged[key].extend(page.get(key) or [])
        return merged

    def delete(self, collection: str, ids: list[str] | None = None,
               where: dict | None = None) -> int:
        col = self._col(collection)
        doomed: set[str] = set()
        if ids:
            doomed |= set(self._by_ids(col, list(ids), [])["ids"])
        if where is not None:
            doomed |= set(self._pages(col, where, [])["ids"])
        doomed_list = list(doomed)
        for start in range(0, len(doomed_list), _PAGE):
            col.delete(ids=doomed_list[start:start + _PAGE])
        return len(doomed)

    def get(self, collection: str, ids: list[str]) -> list[Record]:
        if not ids:
            return []
        result = self._by_ids(self._col(collection), list(ids), ["documents", "metadatas"])
        by_id = {r.id: r for r in self._records(result)}
        return [by_id[i] for i in ids if i in by_id]

    def scan(self, collection: str, where: dict, limit: int | None = None, offset: int = 0,
             with_vectors: bool = False) -> list[Record]:
        include = ["documents", "metadatas"] + (["embeddings"] if with_vectors else [])
        try:
            result = self._pages(self._col(collection), where, include, offset, limit)
        except Exception as e:
            if not with_vectors or _VECTORS_MISSING not in str(e):
                raise
            warnings.warn("Chroma não conseguiu ler os vetores da coleção "
                          f"'{collection}' ({e}); seguindo sem eles (o grafo fica sem as "
                          "ligações de parecidas).", RuntimeWarning, stacklevel=2)
            return self.scan(collection, where, limit, offset, with_vectors=False)
        return self._records(result, with_vectors)

    def count(self, collection: str, where: dict) -> int:
        col = self._col(collection)
        if not where:
            return col.count()
        return len(self._pages(col, where, [])["ids"])

    def dense_search(self, collection: str, vector: list[float], where: dict,
                     limit: int) -> list[Hit]:
        col = self._col(collection)
        result = col.query(query_embeddings=[vector], n_results=limit, where=_where(where),
                           include=["documents", "metadatas", "distances"])
        flat = {key: (value[0] if value else value) for key, value in result.items()
                if key in ("ids", "documents", "metadatas", "distances")}
        records = self._records(flat)
        return [Hit(r, 1.0 - float(d)) for r, d in zip(records, flat["distances"], strict=True)]

    def hybrid_search(self, collection, vector, terms, where, limit):
        raise NotImplementedError("ChromaStore has no native hybrid search")

    def close(self) -> None:
        self._collections.clear()
