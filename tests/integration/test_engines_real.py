"""Real engines, at no cost: local Ollama (native API and its OpenAI-compatible /v1), Gemini free
tier when GEMINI_API_KEY exists, Anthropic only when ANTHROPIC_API_KEY exists.
Run with: pytest -m real_engines tests/integration/test_engines_real.py"""

import math
import os

import httpx
import pytest

from pi_memory import PiMemory
from pi_memory.engines.stores.memory import MemoryStore
from tests.docs import FILES

pytestmark = pytest.mark.real_engines

OLLAMA = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"
CHAT_MODELS = ("qwen2.5:14b", "qwen2.5:7b", "qwen3:8b", "qwen3:4b-instruct")


def _ollama_models() -> set[str]:
    try:
        tags = httpx.get(f"{OLLAMA}/api/tags", timeout=5).json()
    except httpx.HTTPError:
        return set()
    return {m["name"] for m in tags.get("models", [])}


MODELS = _ollama_models()
CHAT = next((m for m in CHAT_MODELS if m in MODELS), None)
needs_ollama_embed = pytest.mark.skipif(
    not any(m.startswith(EMBED_MODEL) for m in MODELS),
    reason=f"Ollama fechado ou sem o modelo {EMBED_MODEL} (ollama pull {EMBED_MODEL})")
needs_ollama_chat = pytest.mark.skipif(CHAT is None, reason="Ollama sem modelo de conversa")
needs_gemini = pytest.mark.skipif(not os.environ.get("GEMINI_API_KEY"),
                                  reason="GEMINI_API_KEY não definida")
needs_anthropic = pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"),
                                     reason="ANTHROPIC_API_KEY não definida")


def _check_embedder(embedder):
    vectors = embedder.embed_documents(["O gato dorme no sofá.", "O carro está na garagem."])
    query = embedder.embed_query("onde o felino está dormindo?")
    assert len(query) == embedder.dimension and abs(math.sqrt(sum(v * v for v in query)) - 1) < 1e-6
    cat, car = (sum(a * b for a, b in zip(query, v, strict=True)) for v in vectors)
    assert cat > car


def _check_documents(embedder):
    with PiMemory(embedder=embedder, llm=lambda p: "", store=MemoryStore()) as pm:
        for name in ("manual.txt", "estoque.csv", "notas.md"):
            pm.documents.add_bytes(name, FILES[name], owner="teste")
        top = pm.documents.search("de quanto em quanto tempo usar o descalcificante?",
                                  owner="teste", limit=3)["results"]
        assert top[0]["citation"]["source"] == "manual.txt"


@needs_ollama_embed
def test_ollama_embedder():
    from pi_memory.embedders import OllamaEmbedder
    embedder = OllamaEmbedder(EMBED_MODEL)
    assert embedder.dimension == 768
    _check_embedder(embedder)
    _check_documents(embedder)


@needs_ollama_embed
def test_openai_format_embedder_against_ollama_v1():
    from pi_memory.embedders import OpenAIEmbedder
    _check_embedder(OpenAIEmbedder(EMBED_MODEL, base_url=f"{OLLAMA}/v1"))


@needs_ollama_chat
def test_openai_format_llm_against_ollama_v1():
    from pi_memory.llms import OpenAILLM
    answer = OpenAILLM(CHAT, base_url=f"{OLLAMA}/v1", timeout=180).complete(
        "Responda apenas com a palavra OK, sem mais nada.")
    assert "OK" in answer.upper()


@needs_gemini
def test_gemini_embedder():
    from pi_memory.embedders import GeminiEmbedder
    embedder = GeminiEmbedder()
    _check_embedder(embedder)
    _check_documents(embedder)


@needs_gemini
def test_gemini_llm_in_the_memory_flow():
    from pi_memory.llms import GeminiLLM
    model = os.environ.get("PI_MEMORY_TEST_GEMINI_MODEL", "gemini-3.5-flash")
    with PiMemory(embedder=_small_local_or_fake(), llm=GeminiLLM(model, timeout=120),
                  store=MemoryStore()) as pm:
        decisions = pm.memories.add("meu nome é Ana Exemplo e moro em Curitiba",
                                    owner="teste")["decisions"]
        assert [d["event"] for d in decisions].count("add") >= 1
        texts = " ".join(m["text"].casefold() for m in pm.memories.list(owner="teste")["memories"])
        assert "curitiba" in texts


@needs_anthropic
def test_anthropic_llm():
    from pi_memory.llms import AnthropicLLM
    model = os.environ.get("PI_MEMORY_TEST_ANTHROPIC_MODEL")
    if not model:
        pytest.skip("PI_MEMORY_TEST_ANTHROPIC_MODEL não definida (nome do modelo da Anthropic)")
    answer = AnthropicLLM(model).complete("Responda apenas com a palavra OK, sem mais nada.")
    assert "OK" in answer.upper()


def _small_local_or_fake():
    if any(m.startswith(EMBED_MODEL) for m in MODELS):
        from pi_memory.embedders import OllamaEmbedder
        return OllamaEmbedder(EMBED_MODEL)
    from tests.fakes import FakeEmbedder
    return FakeEmbedder()
