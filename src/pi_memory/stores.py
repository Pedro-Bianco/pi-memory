"""Public import point for the included vector stores.
Nothing is imported until a name is used, so an
engine's optional dependency is only needed when that engine is chosen."""

import importlib

_NAMES = {
    "QdrantStore": "pi_memory.engines.stores.qdrant",
    "MemoryStore": "pi_memory.engines.stores.memory",
    "ChromaStore": "pi_memory.engines.stores.chroma",
}

__all__ = sorted(_NAMES)


def __getattr__(name: str):
    if name not in _NAMES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(_NAMES[name]), name)
