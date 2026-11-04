"""The only place outside the engine packages that names concrete implementations: what PiMemory()
uses when the developer does not choose (FastEmbed + Ollama + Qdrant local: local by default).
Imports are lazy so an engine's optional dependency is only needed when it is used."""

from __future__ import annotations

from pi_memory import config


def embedder():
    from pi_memory.engines.embedders.fastembed import FastEmbedEmbedder
    return FastEmbedEmbedder()


def llm(timeout: float):
    from pi_memory.engines.llms.ollama import OllamaLLM
    return OllamaLLM(timeout=timeout)


def as_llm(value):
    """A callable str -> str is accepted as the language model."""
    if hasattr(value, "complete"):
        return value
    if callable(value):
        from pi_memory.engines.llms.function import FunctionLLM
        return FunctionLLM(value)
    raise TypeError("llm deve ter um método complete(prompt) ou ser uma função str -> str")


def store(path: str | None, timeout: float):
    from pi_memory.engines.stores.qdrant import QdrantStore
    return QdrantStore(path=path or config.DEFAULT_PATH, timeout=timeout)


def prompts():
    from pi_memory.prompts.portuguese import PortuguesePrompts
    return PortuguesePrompts()


def chunker():
    from pi_memory.chunking import SentenceChunker
    return SentenceChunker()


def renderer():
    from pi_memory.render.html import HtmlGraphRenderer
    return HtmlGraphRenderer()


def reader_registry(custom):
    from pi_memory.readers.registry import ReaderRegistry
    return ReaderRegistry(custom)


# type name in a config file → (module, class) of the engine
ENGINES = {
    "embedder": {
        "fastembed": ("pi_memory.engines.embedders.fastembed", "FastEmbedEmbedder"),
        "ollama": ("pi_memory.engines.embedders.ollama", "OllamaEmbedder"),
        "openai": ("pi_memory.engines.embedders.openai", "OpenAIEmbedder"),
        "gemini": ("pi_memory.engines.embedders.gemini", "GeminiEmbedder"),
    },
    "llm": {
        "ollama": ("pi_memory.engines.llms.ollama", "OllamaLLM"),
        "openai": ("pi_memory.engines.llms.openai", "OpenAILLM"),
        "gemini": ("pi_memory.engines.llms.gemini", "GeminiLLM"),
        "anthropic": ("pi_memory.engines.llms.anthropic", "AnthropicLLM"),
    },
    "store": {
        "qdrant": ("pi_memory.engines.stores.qdrant", "QdrantStore"),
        "memory": ("pi_memory.engines.stores.memory", "MemoryStore"),
        "chroma": ("pi_memory.engines.stores.chroma", "ChromaStore"),
    },
}
_TIMED = {"OllamaEmbedder", "OpenAIEmbedder", "GeminiEmbedder", "OllamaLLM", "OpenAILLM",
          "GeminiLLM", "AnthropicLLM", "QdrantStore"}


def build(kind: str, spec, timeout: float, path: str | None):
    """One engine from its config entry, e.g. {"type": "ollama", "model": "nomic-embed-text"}."""
    import importlib

    from pi_memory.errors import InvalidInputError

    if not isinstance(spec, dict) or "type" not in spec:
        raise InvalidInputError(f"'{kind}' precisa ser um objeto com 'type'.")
    options = {k: v for k, v in spec.items() if k != "type"}
    secret = [k for k in options if "key" in k.lower() or "token" in k.lower()]
    if secret:
        raise InvalidInputError(
            f"Chaves de API não vão no arquivo de configuração ({', '.join(secret)}): defina a "
            "variável de ambiente do motor (OPENAI_API_KEY, GEMINI_API_KEY, ANTHROPIC_API_KEY).")
    known = ENGINES[kind]
    if spec["type"] not in known:
        raise InvalidInputError(f"Tipo de {kind} '{spec['type']}' desconhecido. Aceitos: "
                                f"{', '.join(sorted(known))}.")
    module, name = known[spec["type"]]
    cls = getattr(importlib.import_module(module), name)
    if name in _TIMED:
        options.setdefault("timeout", timeout)
    if name == "QdrantStore" and "url" not in options:
        options.setdefault("path", path or config.DEFAULT_PATH)
    try:
        return cls(**options)
    except TypeError as e:
        raise InvalidInputError(f"Opções inválidas para {kind} '{spec['type']}': {e}") from None
