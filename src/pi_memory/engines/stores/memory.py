"""In-memory vector store with no dependencies: tests, small uses and the reference behaviour of
the VectorStore contract. With `path`, it is saved to a JSON file after every write."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

from pi_memory.errors import NotFoundError
from pi_memory.interfaces import Hit, Record
from pi_memory.search import matches


def _normalized(vector: list[float] | None) -> list[float] | None:
    if vector is None:
        return None
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector] if norm else list(vector)


def _copy(record: Record, with_vector: bool = False) -> Record:
    """Callers may change what they get back; the stored record only changes through upsert."""
    payload = {k: dict(v) if isinstance(v, dict) else v for k, v in record.payload.items()}
    return Record(record.id, record.text, payload,
                  list(record.vector) if with_vector and record.vector else None,
                  dict(record.terms) if record.terms else None)


class MemoryStore:
    native_hybrid = False

    def __init__(self, path: str | os.PathLike | None = None):
        self.path = Path(path) if path else None
        self._meta: dict[str, dict] = {}
        self._data: dict[str, dict[str, Record]] = {}
        if self.path and self.path.exists():
            self._load()

    def _load(self) -> None:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self._meta = raw.get("meta", {})
        self._data = {
            name: {r["id"]: Record(**r) for r in records}
            for name, records in raw.get("collections", {}).items()
        }

    def _save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        raw = {
            "meta": self._meta,
            "collections": {
                name: [r.__dict__ for r in records.values()]
                for name, records in self._data.items()
            },
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    def _collection(self, name: str) -> dict[str, Record]:
        if name not in self._data:
            raise NotFoundError(f"A coleção '{name}' não existe.")
        return self._data[name]

    def open_collection(self, name: str, dimension: int, meta: dict) -> dict:
        if name not in self._meta:
            self._meta[name] = dict(meta)
            self._data.setdefault(name, {})
            self._save()
        return dict(self._meta[name])

    def set_meta(self, name: str, meta: dict) -> None:
        self._meta[name] = dict(meta)
        self._save()

    def upsert(self, collection: str, records: list[Record]) -> None:
        target = self._collection(collection)
        for r in records:
            target[r.id] = Record(r.id, r.text, dict(r.payload), _normalized(r.vector),
                                  dict(r.terms) if r.terms else None)
        self._save()

    def delete(self, collection: str, ids: list[str] | None = None,
               where: dict | None = None) -> int:
        target = self._collection(collection)
        doomed = set(ids or [])
        if where is not None:
            doomed |= {i for i, r in target.items() if matches(r.payload, where)}
        removed = 0
        for item_id in doomed:
            if target.pop(item_id, None) is not None:
                removed += 1
        if removed:
            self._save()
        return removed

    def get(self, collection: str, ids: list[str]) -> list[Record]:
        target = self._collection(collection)
        return [_copy(target[i]) for i in ids if i in target]

    def scan(self, collection: str, where: dict, limit: int | None = None, offset: int = 0,
             with_vectors: bool = False) -> list[Record]:
        found = [r for r in self._collection(collection).values() if matches(r.payload, where)]
        found = found[offset:offset + limit if limit is not None else None]
        return [_copy(r, with_vectors) for r in found]

    def count(self, collection: str, where: dict) -> int:
        return sum(1 for r in self._collection(collection).values() if matches(r.payload, where))

    def dense_search(self, collection: str, vector: list[float], where: dict,
                     limit: int) -> list[Hit]:
        query = _normalized(vector)
        hits = [
            Hit(_copy(r), sum(a * b for a, b in zip(query, r.vector, strict=True)))
            for r in self._collection(collection).values()
            if r.vector is not None and matches(r.payload, where)
        ]
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]

    def hybrid_search(self, collection, vector, terms, where, limit):
        raise NotImplementedError("MemoryStore has no native hybrid search")

    def close(self) -> None:
        self._save()
