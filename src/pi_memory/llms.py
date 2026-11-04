"""Public import point for the included language models.
Nothing is imported until a name is used, so an
engine's optional dependency is only needed when that engine is chosen."""

import importlib

_NAMES = {
    "OllamaLLM": "pi_memory.engines.llms.ollama",
    "OpenAILLM": "pi_memory.engines.llms.openai",
    "GeminiLLM": "pi_memory.engines.llms.gemini",
    "AnthropicLLM": "pi_memory.engines.llms.anthropic",
    "FunctionLLM": "pi_memory.engines.llms.function",
}

__all__ = sorted(_NAMES)


def __getattr__(name: str):
    if name not in _NAMES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(_NAMES[name]), name)
