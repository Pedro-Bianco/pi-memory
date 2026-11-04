"""Public import point for the included embedding engines.
Nothing is imported until a name is used, so an
engine's optional dependency is only needed when that engine is chosen."""

import importlib

_NAMES = {
    "FastEmbedEmbedder": "pi_memory.engines.embedders.fastembed",
    "OllamaEmbedder": "pi_memory.engines.embedders.ollama",
    "OpenAIEmbedder": "pi_memory.engines.embedders.openai",
    "GeminiEmbedder": "pi_memory.engines.embedders.gemini",
}

__all__ = sorted(_NAMES)


def __getattr__(name: str):
    if name not in _NAMES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(_NAMES[name]), name)
