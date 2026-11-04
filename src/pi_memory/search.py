"""Hybrid search: meaning (dense vectors) + exact word, fused with DBSF.

Exact word: the dense vector ties on codes — "2024-0815" and "2024-0816" scored 0.859 both — while
a term vector separates them (original project, 2026-11-01). Fusion: RRF only looks at
positions and lost "contrato 2024-0815" to "2024-0816"; DBSF keeps the margin of the word match
and got all four test questions first (original project, 2026-11-01). Stores with native hybrid
search (Qdrant) do it themselves with the same terms; for the others the library keeps a BM25
index in memory and fuses with the same DBSF formula, so results have the same shape everywhere.
"""

from __future__ import annotations

import math
import re
import statistics
from collections.abc import Iterable

from pi_memory import config
from pi_memory._util import plain
from pi_memory.interfaces import Hit, Record, VectorStore

_WORD = re.compile(r"[a-z0-9]+(?:[-./][a-z0-9]+)*")


def tokens(text: str) -> list[str]:
    """Lowercase, no accents; codes like "nf-4521" kept whole AND split into their parts.
    One-character parts are dropped: the "2" of "7.2" matched "2%" and put the wrong page first
    (eval documents 2026-11-04: exact terms in Qdrant 10/12 → 11/12, library BM25 12/12)."""
    words = _WORD.findall(plain(text))
    parts = [p for w in words for p in re.split(r"[-./]", w) if len(p) > 1 and p != w]
    return words + parts


def terms(text: str) -> dict[str, float]:
    counts: dict[str, float] = {}
    for token in tokens(text):
        counts[token] = counts.get(token, 0.0) + 1.0
    return counts


def matches(payload: dict, where: dict | None) -> bool:
    """Equality filter shared by the library-side search and the in-memory store.
    "metadata.key" looks inside payload["metadata"]."""
    for key, value in (where or {}).items():
        if key.startswith("metadata."):
            actual = (payload.get("metadata") or {}).get(key[len("metadata."):])
        else:
            actual = payload.get(key)
        if actual != value:
            return False
    return True


class BM25Index:
    """BM25 over the texts of one collection, kept in the memory of this process. Writes made by
    another process are only seen after the index is rebuilt (a new PiMemory)."""

    K1 = 1.2
    B = 0.75

    def __init__(self) -> None:
        self._docs: dict[str, tuple[dict[str, float], dict]] = {}
        self._df: dict[str, int] = {}
        self._total_len = 0.0

    def __len__(self) -> int:
        return len(self._docs)

    def add(self, record: Record) -> None:
        self.remove([record.id])
        doc_terms = record.terms if record.terms is not None else terms(record.text)
        self._docs[record.id] = (doc_terms, dict(record.payload))
        self._total_len += sum(doc_terms.values())
        for term in doc_terms:
            self._df[term] = self._df.get(term, 0) + 1

    def remove(self, ids: Iterable[str]) -> None:
        for doc_id in ids:
            entry = self._docs.pop(doc_id, None)
            if entry is None:
                continue
            doc_terms = entry[0]
            self._total_len -= sum(doc_terms.values())
            for term in doc_terms:
                self._df[term] -= 1
                if self._df[term] <= 0:
                    del self._df[term]

    def remove_where(self, where: dict) -> None:
        self.remove([i for i, (_, payload) in self._docs.items() if matches(payload, where)])

    def search(self, query_terms: dict[str, float], where: dict | None,
               limit: int) -> list[tuple[str, float]]:
        n = len(self._docs)
        if not n or not query_terms:
            return []
        avg_len = self._total_len / n or 1.0
        idf = {t: math.log(1 + (n - self._df[t] + 0.5) / (self._df[t] + 0.5))
               for t in query_terms if t in self._df}
        if not idf:
            return []
        scored = []
        for doc_id, (doc_terms, payload) in self._docs.items():
            if not matches(payload, where):
                continue
            length = sum(doc_terms.values())
            score = 0.0
            for term, weight in idf.items():
                tf = doc_terms.get(term, 0.0)
                if tf:
                    norm = tf + self.K1 * (1 - self.B + self.B * length / avg_len)
                    score += weight * tf * (self.K1 + 1) / norm
            if score > 0:
                scored.append((doc_id, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]


def _dbsf_normalize(scores: list[float]) -> list[float]:
    if len(scores) < 2:
        return [0.5 for _ in scores]
    mean = statistics.fmean(scores)
    std = statistics.pstdev(scores)
    if std == 0:
        return [0.5 for _ in scores]
    low, high = mean - 3 * std, mean + 3 * std
    return [min(1.0, max(0.0, (s - low) / (high - low))) for s in scores]


def dbsf_fuse(lists: list[list[tuple[str, float]]], limit: int) -> list[tuple[str, float]]:
    """Distribution-Based Score Fusion: each list normalized by mean ± 3 standard deviations,
    then summed per id (same idea as Qdrant's Fusion.DBSF)."""
    fused: dict[str, float] = {}
    for ranked in lists:
        normalized = _dbsf_normalize([score for _, score in ranked])
        for (item_id, _), value in zip(ranked, normalized, strict=True):
            fused[item_id] = fused.get(item_id, 0.0) + value
    return sorted(fused.items(), key=lambda item: item[1], reverse=True)[:limit]


def hybrid(store: VectorStore, collection: str, vector: list[float], query: str, where: dict,
           limit: int, index: BM25Index | None) -> list[Hit]:
    """Same result shape whether the store fuses natively or the library does it."""
    query_terms = terms(query)
    if store.native_hybrid:
        return store.hybrid_search(collection, vector, query_terms, where, limit)
    dense = store.dense_search(collection, vector, where, config.HYBRID_PREFETCH)
    keyword = index.search(query_terms, where, config.HYBRID_PREFETCH) if index else []
    fused = dbsf_fuse([[(h.record.id, h.score) for h in dense], keyword], limit)
    records = {h.record.id: h.record for h in dense}
    missing = [item_id for item_id, _ in fused if item_id not in records]
    if missing:
        records.update({r.id: r for r in store.get(collection, missing)})
    return [Hit(records[item_id], score) for item_id, score in fused if item_id in records]
