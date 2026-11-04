"""The swappable pieces (docs/GUIA.md, section 15). Implementations do not need to inherit from
these protocols; they only need the same attributes and methods."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class Record:
    id: str
    text: str
    payload: dict = field(default_factory=dict)
    vector: list[float] | None = None
    terms: dict[str, float] | None = None


@dataclass
class Hit:
    record: Record
    score: float


@dataclass
class Section:
    location: str
    text: str


@dataclass
class ChunkText:
    location: str
    text: str


@dataclass
class ExtractedFact:
    text: str
    stopped_being_true: bool = False


@runtime_checkable
class Embedder(Protocol):
    name: str

    @property
    def dimension(self) -> int: ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


@runtime_checkable
class LLM(Protocol):
    def complete(self, prompt: str) -> str: ...


@runtime_checkable
class VectorStore(Protocol):
    native_hybrid: bool

    def open_collection(self, name: str, dimension: int, meta: dict) -> dict: ...

    def set_meta(self, name: str, meta: dict) -> None: ...

    def upsert(self, collection: str, records: list[Record]) -> None: ...

    def delete(self, collection: str, ids: list[str] | None = None,
               where: dict | None = None) -> int: ...

    def get(self, collection: str, ids: list[str]) -> list[Record]: ...

    def scan(self, collection: str, where: dict, limit: int | None = None, offset: int = 0,
             with_vectors: bool = False) -> list[Record]: ...

    def count(self, collection: str, where: dict) -> int: ...

    def dense_search(self, collection: str, vector: list[float], where: dict,
                     limit: int) -> list[Hit]: ...

    def hybrid_search(self, collection: str, vector: list[float], terms: dict[str, float],
                      where: dict, limit: int) -> list[Hit]: ...

    def close(self) -> None: ...


@runtime_checkable
class DocumentReader(Protocol):
    extensions: frozenset[str]

    def read(self, data: bytes, filename: str) -> list[Section]: ...


@runtime_checkable
class Chunker(Protocol):
    def split(self, sections: list[Section]) -> list[ChunkText]: ...


@runtime_checkable
class PromptSet(Protocol):
    def extraction(self, conversation: list[dict]) -> str: ...

    def parse_extraction(self, raw: str) -> list[ExtractedFact]: ...

    def topics(self, facts: list[str], topics: Sequence[str]) -> str: ...

    def parse_topics(self, raw: str, count: int, topics: Sequence[str]) -> list[str]: ...

    def decision(self, fact: ExtractedFact, candidates: list[str]) -> str: ...

    def parse_decision(self, raw: str, candidate_count: int) -> tuple[str, int | None] | None: ...


@runtime_checkable
class GraphRenderer(Protocol):
    def render(self, graph: dict) -> str: ...
