"""quickstart.md step 2 with real engines: FastEmbed + Ollama + Qdrant local.
The language model is the first installed of CHAT_MODELS (qwen2.5:14b, the default, first).
Run with: pytest -m real_engines"""

import pytest

from pi_memory import PiMemory
from pi_memory.llms import OllamaLLM
from tests.integration.test_engines_real import CHAT

pytestmark = [pytest.mark.real_engines,
              pytest.mark.skipif(CHAT is None, reason="Ollama sem modelo de conversa")]


def test_move_replaces_city(tmp_path):
    with PiMemory(path=str(tmp_path / "data"), llm=OllamaLLM(CHAT, timeout=180)) as pm:
        first = pm.memories.add("meu nome é Ana Exemplo e moro em Curitiba", owner="ana")
        assert [d["event"] for d in first["decisions"]].count("add") >= 1
        second = pm.memories.add("me mudei para Recife", owner="ana")
        assert any(d["event"] == "update" for d in second["decisions"])
        texts = [m["text"].casefold() for m in pm.memories.list(owner="ana")["memories"]]
        assert any("recife" in t for t in texts)
        assert not any("curitiba" in t for t in texts)
        # Recall is "the 3 closest" (as in the original project): with two memories, "Ana" in the
        # question matched the name memory by exact word and came first on 2026-11-04.
        found = pm.memories.search("onde a Ana mora?", owner="ana")["results"]
        assert any("recife" in r["text"].casefold() for r in found)
