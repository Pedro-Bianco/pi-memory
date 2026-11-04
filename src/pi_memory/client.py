"""PiMemory: the object the developer creates. It holds the chosen pieces, opens the collections
and exposes .memories, .documents and .graph. No global state: two objects are independent."""

from __future__ import annotations

import threading
from collections.abc import Sequence

from pi_memory import config, defaults
from pi_memory.errors import EmbedderMismatchError, InvalidInputError
from pi_memory.interfaces import Embedder, PromptSet, Record, VectorStore
from pi_memory.search import BM25Index, terms

_CONFIG_KEYS = {"path", "embedder", "llm", "store", "topics", "timeout", "collection_prefix"}


def _wanted(embedder: Embedder) -> dict:
    return {"embedder": embedder.name, "dimension": embedder.dimension,
            "schema_version": config.SCHEMA_VERSION}


class PiMemory:
    def __init__(self, path: str | None = None, *, embedder: Embedder | None = None,
                 llm=None, store: VectorStore | None = None, readers: Sequence | None = None,
                 chunker=None, prompts: PromptSet | None = None, renderer=None,
                 topics: Sequence[str] | None = None,
                 collection_prefix: str = config.COLLECTION_PREFIX,
                 timeout: float = config.TIMEOUT_S):
        self.timeout = timeout
        self.store = store if store is not None else defaults.store(path, timeout)
        try:
            self.embedder = embedder if embedder is not None else defaults.embedder()
            self.llm = defaults.as_llm(llm) if llm is not None else defaults.llm(timeout)
            self.prompts = prompts if prompts is not None else defaults.prompts()
            self.readers = list(readers or [])
            self.chunker = chunker if chunker is not None else defaults.chunker()
            self.reader_registry = defaults.reader_registry(self.readers)
            self.renderer = renderer if renderer is not None else defaults.renderer()
            self.topics = tuple(topics or config.DEFAULT_TOPICS)
            self.lock = threading.RLock()
            # base names; after a reindex the data lives in "<base>_v<n>" and the base collection
            # keeps a pointer to it ("active" in its meta)
            self._bases = {"memories": f"{collection_prefix}_memories",
                           "chunks": f"{collection_prefix}_chunks"}
            self.memories_collection = self._open(self._bases["memories"])
            self.chunks_collection = self._open(self._bases["chunks"])
        except BaseException:
            self.store.close()
            raise
        self._indexes: dict[str, BM25Index] = {}
        self._memories = None
        self._documents = None
        self._graph = None

    def _open(self, base: str) -> str:
        """Opens the active collection of `base` and refuses another embedder's vectors."""
        wanted = _wanted(self.embedder)
        stored = self.store.open_collection(base, wanted["dimension"], wanted)
        name = stored.get("active", base)
        if name != base:
            stored = self.store.open_collection(name, wanted["dimension"], wanted)
        if (stored.get("embedder"), stored.get("dimension")) != (wanted["embedder"],
                                                                  wanted["dimension"]):
            raise EmbedderMismatchError(
                f"A coleção '{name}' foi criada com o embedding '{stored.get('embedder')}' "
                f"({stored.get('dimension')} dimensões), mas agora o embedding é "
                f"'{wanted['embedder']}' ({wanted['dimension']} dimensões). Vetores de modelos "
                "diferentes não se misturam: volte ao modelo anterior, ou abra com ele e chame "
                "pm.reindex(novo_embedder) para regravar tudo com o novo."
            )
        return name

    def reindex(self, new_embedder: Embedder) -> dict:
        """Re-embeds every memory and piece with another model, into new collections, and switches
        to them. The old collections are only emptied after both new ones are complete, so a
        failure halfway leaves everything as it was."""
        with self.lock:
            new_meta = _wanted(new_embedder)
            plan = []
            for kind, base in self._bases.items():
                base_meta = self.store.open_collection(base, new_meta["dimension"], new_meta)
                version = int(base_meta.get("version", 1)) + 1
                target = f"{base}_v{version}"
                self.store.open_collection(target, new_meta["dimension"], new_meta)
                self.store.delete(target, where={})   # leftovers of an interrupted attempt
                current = getattr(self, f"{kind}_collection")
                records = self.store.scan(current, {})
                for start in range(0, len(records), config.EMBED_BATCH):
                    batch = records[start:start + config.EMBED_BATCH]
                    vectors = new_embedder.embed_documents([r.text for r in batch])
                    self.store.upsert(target, [
                        Record(r.id, r.text, r.payload, v, terms(r.text))
                        for r, v in zip(batch, vectors, strict=True)])
                plan.append((kind, base, base_meta, version, current, target, len(records)))
            for kind, base, base_meta, version, _current, target, _count in plan:
                self.store.set_meta(base, {**base_meta, "active": target, "version": version})
                setattr(self, f"{kind}_collection", target)
            for _kind, _base, _meta, _version, current, _target, _count in plan:
                self.store.delete(current, where={})
            self.embedder = new_embedder
            self._indexes.clear()
            self._memories = self._documents = None
            counts = {kind: count for kind, *_, count in plan}
            return {**counts, "embedder": new_embedder.name}

    @classmethod
    def from_config(cls, settings: dict, **overrides) -> PiMemory:
        """Builds from a JSON-like dict (used by the CLI and the servers):
        {"path": ..., "embedder": {"type": "ollama", "model": ...}, "llm": {...},
         "store": {"type": "qdrant", ...}, "topics": [...], "timeout": 60}.
        API keys never go in the file: each engine reads its environment variable.
        Objects passed as keyword arguments win over the file."""
        if not isinstance(settings, dict):
            raise InvalidInputError("A configuração precisa ser um objeto JSON.")
        unknown = set(settings) - _CONFIG_KEYS
        if unknown:
            raise InvalidInputError(f"Chaves desconhecidas na configuração: {sorted(unknown)}. "
                                    f"Aceitas: {sorted(_CONFIG_KEYS)}.")
        timeout = float(settings.get("timeout", config.TIMEOUT_S))
        options = {"timeout": timeout}
        for key in ("topics", "collection_prefix"):
            if key in settings:
                options[key] = tuple(settings[key]) if key == "topics" else settings[key]
        for kind in ("embedder", "llm", "store"):
            if kind in settings and kind not in overrides:
                options[kind] = defaults.build(kind, settings[kind], timeout,
                                               settings.get("path"))
        options.update(overrides)
        return cls(settings.get("path"), **options)

    def keyword_index(self, collection: str) -> BM25Index | None:
        """Library-side exact-word index, only for stores without native hybrid search."""
        if self.store.native_hybrid:
            return None
        with self.lock:
            if collection not in self._indexes:
                index = BM25Index()
                for record in self.store.scan(collection, {}):
                    index.add(record)
                self._indexes[collection] = index
            return self._indexes[collection]

    @property
    def memories(self):
        if self._memories is None:
            from pi_memory.memories import MemoryService
            self._memories = MemoryService(self)
        return self._memories

    @property
    def documents(self):
        if self._documents is None:
            from pi_memory.documents import DocumentService
            self._documents = DocumentService(self)
        return self._documents

    @property
    def graph(self):
        if self._graph is None:
            from pi_memory.graph import GraphService
            self._graph = GraphService(self)
        return self._graph

    def stats(self, owner: str) -> dict:
        """Overview of one owner: memories by topic, collections, documents and chunks."""
        from pi_memory import _validate as check
        owner = check.owner(owner)
        by_topic: dict[str, int] = {}
        for record in self.store.scan(self.memories_collection, {"owner": owner}):
            topic = record.payload.get("topic", config.FALLBACK_TOPIC)
            by_topic[topic] = by_topic.get(topic, 0) + 1
        collections = self.documents.collections(owner)["collections"]
        return {
            "owner": owner,
            "memories": {"total": sum(by_topic.values()),
                         "by_topic": dict(sorted(by_topic.items()))},
            "collections": collections,
            "documents": sum(c["documents"] for c in collections),
            "chunks": sum(c["chunks"] for c in collections),
            "engines": {"embedder": self.embedder.name, "dimension": self.embedder.dimension,
                        "store": type(self.store).__name__,
                        "llm": getattr(self.llm, "model", type(self.llm).__name__)},
        }

    def close(self) -> None:
        self.store.close()

    def __enter__(self) -> PiMemory:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
