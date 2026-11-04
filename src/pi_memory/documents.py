"""Knowledge base: documents grouped in named collections (default "geral") per owner, read and
split into pieces (chunks) that remember where they came from, searched by meaning and exact word,
and fully manageable: collections, documents and single chunks can be listed and deleted.

A document has no record of its own: its data travels in the payload of every chunk, and listings
group the chunks by doc_id (so counts stay right after a single chunk is deleted). One kind of
record per store keeps every store implementation simple.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import TYPE_CHECKING

from pi_memory import _validate as check
from pi_memory import config
from pi_memory._util import now_iso, stable_id
from pi_memory.errors import InvalidInputError, NoTextError, NotFoundError, UnreadableDocumentError
from pi_memory.interfaces import Record
from pi_memory.search import hybrid, terms

if TYPE_CHECKING:
    from pi_memory.client import PiMemory

DEFAULT_COLLECTION = "geral"
_COLLECTION = re.compile(r"^[\w][\w .-]{0,99}$")
_DOC_FIELDS = ("owner", "collection", "source", "format", "content_hash", "added_at")


def collection_name(value) -> str:
    if value is None:
        return DEFAULT_COLLECTION
    if not isinstance(value, str) or not _COLLECTION.match(value.strip()):
        raise InvalidInputError("Nome de coleção inválido: use até 100 letras, números, espaço, "
                                "ponto, hífen ou sublinhado (ex. 'contratos').")
    return value.strip()


def _document(payload: dict, chunks: int) -> dict:
    return {"id": payload["doc_id"], **{k: payload.get(k) for k in _DOC_FIELDS},
            "collection": payload.get("collection", DEFAULT_COLLECTION),
            "chunks": chunks, "metadata": dict(payload.get("metadata") or {})}


def _citation(payload: dict) -> dict:
    return {"doc_id": payload.get("doc_id"), "source": payload.get("source"),
            "collection": payload.get("collection", DEFAULT_COLLECTION),
            "location": payload.get("location"),
            "label": f"{payload.get('source')}, {payload.get('location')}"}


def _chunk(record: Record) -> dict:
    p = record.payload
    return {"id": record.id, "doc_id": p.get("doc_id"), "source": p.get("source"),
            "collection": p.get("collection", DEFAULT_COLLECTION), "location": p.get("location"),
            "index": p.get("index"), "text": record.text}


class DocumentService:
    def __init__(self, pm: PiMemory):
        self.pm = pm
        self.collection = pm.chunks_collection

    # ── helpers ──────────────────────────────────────────────────────────────────────────────
    def _index(self):
        return self.pm.keyword_index(self.collection)

    def _remove(self, where: dict | None = None, ids: list[str] | None = None) -> int:
        with self.pm.lock:
            removed = self.pm.store.delete(self.collection, ids=ids, where=where)
            index = self._index()
            if index is not None:
                if where is not None:
                    index.remove_where(where)
                if ids:
                    index.remove(ids)
        return removed

    def _grouped(self, where: dict) -> dict[str, list[Record]]:
        groups: dict[str, list[Record]] = {}
        for record in self.pm.store.scan(self.collection, where):
            groups.setdefault(record.payload.get("doc_id"), []).append(record)
        return groups

    def _owned_chunk(self, chunk_id: str, owner: str) -> Record:
        found = self.pm.store.get(self.collection, [chunk_id]) if isinstance(chunk_id, str) else []
        if not found or found[0].payload.get("owner") != owner:
            raise NotFoundError(f"Trecho '{chunk_id}' não encontrado para o dono '{owner}'.")
        return found[0]

    # ── documents ────────────────────────────────────────────────────────────────────────────
    def add(self, path, owner: str, metadata: dict | None = None,
            collection: str | None = None) -> dict:
        path = Path(path)
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            raise NotFoundError(f"Arquivo não encontrado: {path}") from None
        except OSError as e:
            raise UnreadableDocumentError(f"Não consegui abrir '{path}': {e.strerror}.") from None
        return self.add_bytes(path.name, data, owner, metadata, collection)

    def add_text(self, title: str, text: str, owner: str, collection: str | None = None,
                 metadata: dict | None = None) -> dict:
        """A document typed by the person: stored as Markdown named after the title."""
        if not isinstance(title, str) or not title.strip() or len(title) > 200:
            raise InvalidInputError("Informe um título (title) de até 200 caracteres.")
        if not isinstance(text, str) or not text.strip():
            raise InvalidInputError("O texto (text) do documento não pode ser vazio.")
        title = title.strip()
        filename = title if title.lower().endswith((".md", ".txt")) else f"{title}.md"
        body = text if text.lstrip().startswith("#") else f"# {Path(filename).stem}\n\n{text}"
        return self.add_bytes(filename, body.encode("utf-8"), owner, metadata, collection)

    def add_bytes(self, filename: str, data: bytes, owner: str, metadata: dict | None = None,
                  collection: str | None = None) -> dict:
        owner = check.owner(owner)
        metadata = check.mapping(metadata, "metadata")
        collection = collection_name(collection)
        if not isinstance(filename, str) or not filename.strip():
            raise InvalidInputError("Informe o nome do arquivo (filename), com a extensão.")
        if not isinstance(data, (bytes, bytearray)):
            raise InvalidInputError("O conteúdo do arquivo precisa ser bytes.")
        source = Path(filename).name
        doc_id = stable_id(collection, source, owner=owner)
        content_hash = hashlib.sha256(data).hexdigest()
        where = {"doc_id": doc_id, "owner": owner}

        existing = self.pm.store.scan(self.collection, where)
        if existing and existing[0].payload.get("content_hash") == content_hash:
            return {"document": _document(existing[0].payload, len(existing)),
                    "status": "unchanged", "warnings": []}

        sections = self.pm.reader_registry.read(bytes(data), source)
        pieces = self.pm.chunker.split(sections)
        if not pieces:
            raise NoTextError(
                f"Não encontrei texto em '{source}'. Se for um PDF escaneado (imagem), ele precisa "
                "de OCR, que esta versão não faz; um leitor próprio com OCR pode ser passado em "
                "PiMemory(readers=[...])."
            )
        vectors: list[list[float]] = []
        for start in range(0, len(pieces), config.EMBED_BATCH):
            batch = pieces[start:start + config.EMBED_BATCH]
            vectors.extend(self.pm.embedder.embed_documents([p.text for p in batch]))

        base = {"owner": owner, "collection": collection, "doc_id": doc_id, "source": source,
                "format": Path(source).suffix.lower().lstrip("."), "content_hash": content_hash,
                "added_at": now_iso(), "metadata": metadata}
        records = [Record(stable_id(doc_id, str(i)), piece.text,
                          {**base, "location": piece.location, "index": i}, vector,
                          terms(piece.text))
                   for i, (piece, vector) in enumerate(zip(pieces, vectors, strict=True))]
        with self.pm.lock:
            if existing:
                self._remove(where=where)
            self.pm.store.upsert(self.collection, records)
            index = self._index()
            if index is not None:
                for record in records:
                    index.add(record)
        return {"document": _document(records[0].payload, len(records)),
                "status": "replaced" if existing else "added", "warnings": []}

    def search(self, query: str, owner: str, limit: int = 5, filters: dict | None = None,
               collection: str | None = None) -> dict:
        owner = check.owner(owner)
        query = check.query(query)
        limit = check.limit(limit, 100)
        where = {**check.mapping(filters, "filters"), "owner": owner}
        if collection is not None:
            where["collection"] = collection_name(collection)
        hits = hybrid(self.pm.store, self.collection, self.pm.embedder.embed_query(query), query,
                      where, limit, self._index())
        return {"results": [{"kind": "chunk", "id": h.record.id, "text": h.record.text,
                             "score": h.score, "citation": _citation(h.record.payload)}
                            for h in hits]}

    def list(self, owner: str, collection: str | None = None) -> dict:
        where = {"owner": check.owner(owner)}
        if collection is not None:
            where["collection"] = collection_name(collection)
        documents = [_document(chunks[0].payload, len(chunks))
                     for chunks in self._grouped(where).values()]
        documents.sort(key=lambda d: (d["added_at"] or "", d["id"]), reverse=True)   # id: tie-break
        return {"documents": documents}

    def get(self, doc_id: str, owner: str) -> dict:
        """A document with all its chunks, in order."""
        where = {"doc_id": doc_id, "owner": check.owner(owner)}
        chunks = self.pm.store.scan(self.collection, where)
        if not isinstance(doc_id, str) or not chunks:
            raise NotFoundError(f"Documento '{doc_id}' não encontrado para o dono '{owner}'.")
        chunks.sort(key=lambda r: r.payload.get("index", 0))
        return {"document": _document(chunks[0].payload, len(chunks)),
                "chunks": [_chunk(r) for r in chunks]}

    def remove(self, doc_id: str, owner: str) -> dict:
        where = {"doc_id": doc_id, "owner": check.owner(owner)}
        if not isinstance(doc_id, str) or self.pm.store.count(self.collection, where) == 0:
            raise NotFoundError(f"Documento '{doc_id}' não encontrado para o dono '{owner}'.")
        return {"deleted_chunks": self._remove(where=where)}

    # ── collections ──────────────────────────────────────────────────────────────────────────
    def collections(self, owner: str) -> dict:
        summary: dict[str, dict] = {}
        for chunks in self._grouped({"owner": check.owner(owner)}).values():
            payload = chunks[0].payload
            name = payload.get("collection", DEFAULT_COLLECTION)
            item = summary.setdefault(name, {"name": name, "documents": 0, "chunks": 0,
                                             "updated_at": ""})
            item["documents"] += 1
            item["chunks"] += len(chunks)
            item["updated_at"] = max(item["updated_at"], payload.get("added_at") or "")
        return {"collections": sorted(summary.values(), key=lambda c: c["name"])}

    def delete_collection(self, name: str, owner: str) -> dict:
        where = {"owner": check.owner(owner), "collection": collection_name(name)}
        groups = self._grouped(where)
        if not groups:
            raise NotFoundError(f"Coleção '{name}' não encontrada para o dono '{owner}'.")
        return {"deleted_documents": len(groups), "deleted_chunks": self._remove(where=where)}

    # ── chunks ───────────────────────────────────────────────────────────────────────────────
    def chunks(self, owner: str, doc_id: str | None = None, collection: str | None = None,
               limit: int = 50, offset: int = 0) -> dict:
        where = {"owner": check.owner(owner)}
        if doc_id is not None:
            where["doc_id"] = doc_id
        if collection is not None:
            where["collection"] = collection_name(collection)
        limit = check.limit(limit, 1000)
        offset = check.offset(offset)
        records = self.pm.store.scan(self.collection, where)
        records.sort(key=lambda r: (r.payload.get("collection", ""), r.payload.get("source", ""),
                                    r.payload.get("doc_id", ""), r.payload.get("index", 0)))
        return {"chunks": [_chunk(r) for r in records[offset:offset + limit]],
                "total": len(records)}

    def chunk(self, chunk_id: str, owner: str) -> dict:
        return _chunk(self._owned_chunk(chunk_id, check.owner(owner)))

    def delete_chunk(self, chunk_id: str, owner: str) -> dict:
        self._owned_chunk(chunk_id, check.owner(owner))
        return {"deleted": self._remove(ids=[chunk_id])}
