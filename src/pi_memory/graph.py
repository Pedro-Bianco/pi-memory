"""Memory graph of one owner: topic nodes, memory nodes, each memory linked to its topic and to
the most similar memory of the same topic (a pair only once), using the vectors already stored.

Memories gather around their topic instead of by vector alone: every memory starts with
"O usuário", and on 30 memories in 4 topics only 43-49% of nearest-neighbour links stayed inside
a topic (earlier measurement, 2026-10-31).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

from pi_memory import _validate as check
from pi_memory._util import now_iso

if TYPE_CHECKING:
    from pi_memory.client import PiMemory

_LABEL_CHARS = 40


def _label(text: str) -> str:
    return text if len(text) <= _LABEL_CHARS else text[:_LABEL_CHARS - 1].rstrip() + "…"


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norms = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norms if norms else 0.0


class GraphService:
    def __init__(self, pm: PiMemory):
        self.pm = pm

    def data(self, owner: str, include_documents: bool = False,
             include_chunks: bool = False) -> dict:
        """Memories by topic; with include_documents also the knowledge base (collection →
        document, and with include_chunks each chunk under its document)."""
        owner = check.owner(owner)
        records = self.pm.store.scan(self.pm.memories_collection, {"owner": owner},
                                     with_vectors=True)
        records.sort(key=lambda r: (r.payload.get("topic", ""), r.payload.get("created_at", ""),
                                    r.id))
        groups: dict[str, list] = {}
        for record in records:
            groups.setdefault(record.payload.get("topic") or "outros", []).append(record)

        nodes, edges, linked = [], [], set()
        for topic, members in groups.items():
            nodes.append({"id": f"t:{topic}", "kind": "topic", "label": topic.capitalize(),
                          "topic": topic})
            for record in members:
                nodes.append({"id": f"m:{record.id}", "kind": "memory",
                              "label": _label(record.text), "topic": topic, "text": record.text})
                edges.append({"source": f"m:{record.id}", "target": f"t:{topic}",
                              "kind": "belongs"})
            for record in members:
                best, best_score = None, -2.0
                for other in members:
                    if other.id == record.id or not record.vector or not other.vector:
                        continue
                    score = _cosine(record.vector, other.vector)
                    if score > best_score:
                        best, best_score = other, score
                if best is None:
                    continue
                pair = frozenset((record.id, best.id))
                if pair not in linked:
                    linked.add(pair)
                    edges.append({"source": f"m:{record.id}", "target": f"m:{best.id}",
                                  "kind": "similar", "weight": round(best_score, 4)})
        if include_documents or include_chunks:
            self._knowledge_base(owner, include_chunks, nodes, edges)
        return {"owner": owner, "nodes": nodes, "edges": edges, "generated_at": now_iso()}

    def _knowledge_base(self, owner: str, include_chunks: bool, nodes: list, edges: list) -> None:
        detail = self.pm.documents.chunks(owner, limit=1000)["chunks"] if include_chunks else []
        for collection in self.pm.documents.collections(owner)["collections"]:
            name, group = collection["name"], f"coleção {collection['name']}"
            nodes.append({"id": f"c:{name}", "kind": "collection", "label": name, "topic": group})
            for document in self.pm.documents.list(owner, collection=name)["documents"]:
                doc_node = f"d:{document['id']}"
                nodes.append({"id": doc_node, "kind": "document", "label": document["source"],
                              "topic": group,
                              "text": f"{document['source']} · {document['chunks']} trecho(s)"})
                edges.append({"source": doc_node, "target": f"c:{name}", "kind": "contains"})
                for chunk in (c for c in detail if c["doc_id"] == document["id"]):
                    nodes.append({"id": f"k:{chunk['id']}", "kind": "chunk",
                                  "label": chunk["location"], "topic": group,
                                  "text": chunk["text"]})
                    edges.append({"source": f"k:{chunk['id']}", "target": doc_node,
                                  "kind": "contains"})

    def html(self, owner: str, path: str | None = None, include_documents: bool = True,
             include_chunks: bool = False) -> str:
        """The page as text; with `path`, writes it there and returns the path."""
        page = self.pm.renderer.render(self.data(owner, include_documents, include_chunks))
        if path is None:
            return page
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page, encoding="utf-8")
        return str(target)
