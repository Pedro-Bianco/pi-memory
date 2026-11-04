"""Long-term memory: facts extracted from conversations and kept up to date.

add(): extraction → topic → decision per fact (docs/GUIA.md, section 6). Always the 3 most
similar memories of the same owner go to the model: the "update zone" of the original project
(similarity 0.72-0.89) was measured for e5 only, and the embedder here is swappable. In doubt
the fact is stored and nothing is deleted; an engine failure during extraction raises before
anything is written.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pi_memory import _validate as check
from pi_memory import config
from pi_memory._util import new_id, normalize_text, now_iso
from pi_memory.errors import NotFoundError, PiMemoryError
from pi_memory.interfaces import ExtractedFact, Record
from pi_memory.search import hybrid, terms

if TYPE_CHECKING:
    from pi_memory.client import PiMemory


def _decision(event: str, text: str, memory_id: str | None = None,
              previous_text: str | None = None, topic: str | None = None,
              reason: str | None = None) -> dict:
    return {"event": event, "memory_id": memory_id, "text": text,
            "previous_text": previous_text, "topic": topic, "reason": reason}


def _memory(record: Record) -> dict:
    p = record.payload
    return {"id": record.id, "text": record.text, "owner": p.get("owner"),
            "topic": p.get("topic", config.FALLBACK_TOPIC), "created_at": p.get("created_at"),
            "updated_at": p.get("updated_at"), "metadata": dict(p.get("metadata") or {})}


class MemoryService:
    def __init__(self, pm: PiMemory):
        self.pm = pm
        self.collection = pm.memories_collection

    # ── storage helpers ──────────────────────────────────────────────────────────────────────
    def _index(self):
        return self.pm.keyword_index(self.collection)

    def _write(self, record: Record) -> None:
        record.vector = self.pm.embedder.embed_documents([record.text])[0]
        record.terms = terms(record.text)
        self.pm.store.upsert(self.collection, [record])
        index = self._index()
        if index is not None:
            index.add(record)

    def _remove(self, ids: list[str]) -> int:
        removed = self.pm.store.delete(self.collection, ids=ids)
        index = self._index()
        if index is not None:
            index.remove(ids)
        return removed

    def _owned(self, memory_id: str, owner: str) -> Record:
        found = []
        if isinstance(memory_id, str):
            found = self.pm.store.get(self.collection, [memory_id])
        if not found or found[0].payload.get("owner") != owner:
            raise NotFoundError(f"Memória '{memory_id}' não encontrada para o dono '{owner}'.")
        return found[0]

    def _new(self, text: str, owner: str, topic: str, metadata: dict) -> Record:
        stamp = now_iso()
        record = Record(new_id(), text, {"owner": owner, "topic": topic, "created_at": stamp,
                                         "updated_at": stamp, "metadata": metadata})
        self._write(record)
        return record

    def _similar(self, text: str, owner: str, limit: int) -> list[Record]:
        if config.DECISION_SEARCH == "dense":
            vector = self.pm.embedder.embed_query(text)
            return [h.record for h in self.pm.store.dense_search(
                self.collection, vector, {"owner": owner}, limit)]
        hits = hybrid(self.pm.store, self.collection, self.pm.embedder.embed_query(text), text,
                      {"owner": owner}, limit, self._index())
        return [h.record for h in hits]

    # ── extraction and decision ──────────────────────────────────────────────────────────────
    def _extract(self, conversation: list[dict]) -> list[ExtractedFact]:
        facts: list[ExtractedFact] = []
        seen: set[str] = set()
        window = config.EXTRACTION_WINDOW
        for start in range(0, len(conversation), window):
            prompt = self.pm.prompts.extraction(conversation[start:start + window])
            raw = self.pm.llm.complete(prompt)
            for fact in self.pm.prompts.parse_extraction(raw):
                key = normalize_text(fact.text)
                if key and key not in seen:
                    seen.add(key)
                    fact.text = fact.text[:config.MAX_MEMORY_CHARS]
                    facts.append(fact)
        return facts

    def _topics(self, facts: list[ExtractedFact]) -> list[str]:
        topics = self.pm.topics
        raw = self.pm.llm.complete(self.pm.prompts.topics([f.text for f in facts], topics))
        return self.pm.prompts.parse_topics(raw, len(facts), topics)

    def _apply(self, fact: ExtractedFact, topic: str, owner: str, metadata: dict) -> dict:
        candidates = self._similar(fact.text, owner, config.DECISION_CANDIDATES)
        key = normalize_text(fact.text)
        same = next((c for c in candidates if normalize_text(c.text) == key), None)
        if same is not None:
            return _decision("none", fact.text, same.id, topic=same.payload.get("topic"))
        if not candidates:
            if fact.stopped_being_true:   # nothing to delete, and "no longer true" is not a fact
                return _decision("none", fact.text)
            return self._add(fact, topic, owner, metadata)

        try:
            raw = self.pm.llm.complete(self.pm.prompts.decision(fact, [c.text for c in candidates]))
        except PiMemoryError:
            return self._add(fact, topic, owner, metadata, "fallback_engine_error")
        parsed = self.pm.prompts.parse_decision(raw, len(candidates))
        if parsed is None:
            return self._add(fact, topic, owner, metadata, "fallback_unclear")
        action, index = parsed
        if action == "ADD":
            return self._add(fact, topic, owner, metadata)
        if action == "DUPLICATE":
            return _decision("none", fact.text)

        target = candidates[index]
        try:
            target = self._owned(target.id, owner)     # still there, still this owner's
        except NotFoundError:
            return self._add(fact, topic, owner, metadata, "fallback_target_missing")
        if action == "UPDATE":
            previous = target.text
            target.text = fact.text
            target.payload["topic"] = topic
            target.payload["updated_at"] = now_iso()
            self._write(target)
            return _decision("update", fact.text, target.id, previous, topic)
        self._remove([target.id])
        return _decision("delete", fact.text, target.id, target.text,
                         target.payload.get("topic"))

    def _add(self, fact: ExtractedFact, topic: str, owner: str, metadata: dict,
             reason: str | None = None) -> dict:
        record = self._new(fact.text, owner, topic, metadata)
        return _decision("add", fact.text, record.id, topic=topic, reason=reason)

    # ── public API ───────────────────────────────────────────────────────────────────────────
    def add(self, messages, owner: str, metadata: dict | None = None) -> dict:
        owner = check.owner(owner)
        conversation = check.messages(messages)
        metadata = check.mapping(metadata, "metadata")
        facts = self._extract(conversation)
        if not facts:
            return {"decisions": []}
        topics = self._topics(facts)
        with self.pm.lock:
            return {"decisions": [self._apply(fact, topic, owner, metadata)
                                  for fact, topic in zip(facts, topics, strict=True)]}

    def remember(self, text: str, owner: str, topic: str | None = None,
                 metadata: dict | None = None) -> dict:
        owner = check.owner(owner)
        text = check.text(text)
        if topic is None:
            topics = self.pm.topics
            topic = config.FALLBACK_TOPIC if config.FALLBACK_TOPIC in topics else topics[-1]
        else:
            topic = check.topic(topic, self.pm.topics)
        with self.pm.lock:
            return _memory(self._new(text, owner, topic, check.mapping(metadata, "metadata")))

    def search(self, query: str, owner: str, limit: int = 3, filters: dict | None = None) -> dict:
        owner = check.owner(owner)
        query = check.query(query)
        limit = check.limit(limit, 100)
        where = {**check.mapping(filters, "filters"), "owner": owner}
        hits = hybrid(self.pm.store, self.collection, self.pm.embedder.embed_query(query), query,
                      where, limit, self._index())
        return {"results": [{"kind": "memory", "id": h.record.id, "text": h.record.text,
                             "score": h.score, "memory": _memory(h.record)} for h in hits]}

    def get(self, memory_id: str, owner: str) -> dict:
        return _memory(self._owned(memory_id, check.owner(owner)))

    def list(self, owner: str, topic: str | None = None, limit: int = 100,
             offset: int = 0) -> dict:
        where = {"owner": check.owner(owner)}
        if topic is not None:
            where["topic"] = topic
        limit = check.limit(limit, 1000)
        offset = check.offset(offset)
        records = self.pm.store.scan(self.collection, where)
        # the id breaks ties: on Windows the clock moves in ~15 ms steps, so memories saved together
        # share updated_at, and without a tie-break the order (and offset paging) could change
        # between calls
        records.sort(key=lambda r: (r.payload.get("updated_at", ""), r.id), reverse=True)
        return {"memories": [_memory(r) for r in records[offset:offset + limit]],
                "total": len(records)}

    def update(self, memory_id: str, owner: str, text: str | None = None,
               topic: str | None = None, metadata: dict | None = None) -> dict:
        owner = check.owner(owner)
        with self.pm.lock:
            record = self._owned(memory_id, owner)
            if text is not None:
                record.text = check.text(text)
            if topic is not None:
                record.payload["topic"] = check.topic(topic, self.pm.topics)
            if metadata is not None:
                record.payload["metadata"] = check.mapping(metadata, "metadata")
            record.payload["updated_at"] = now_iso()
            self._write(record)
            return _memory(record)

    def delete(self, memory_id: str, owner: str) -> dict:
        owner = check.owner(owner)
        with self.pm.lock:
            self._owned(memory_id, owner)
            return {"deleted": self._remove([memory_id])}

    def delete_all(self, owner: str) -> dict:
        where = {"owner": check.owner(owner)}
        with self.pm.lock:
            removed = self.pm.store.delete(self.collection, where=where)
            index = self._index()
            if index is not None:
                index.remove_where(where)
            return {"deleted": removed}
