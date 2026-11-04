"""every piece is swapped only in the configuration."""

import pytest

from pi_memory import EmbedderMismatchError, InvalidInputError, PiMemory
from pi_memory.engines.stores.memory import MemoryStore
from pi_memory.interfaces import ChunkText, ExtractedFact, Section
from pi_memory.prompts.portuguese import PortuguesePrompts
from tests.fakes import FakeEmbedder, ScriptedLLM, make_pm


class XyzReader:
    extensions = frozenset({".xyz"})

    def read(self, data, filename):
        return [Section("bloco único", data.decode("utf-8"))]


class OneChunk:
    def split(self, sections):
        return [ChunkText("tudo", " ".join(s.text for s in sections))]


def test_custom_reader_and_chunker_are_used():
    with make_pm(readers=[XyzReader()], chunker=OneChunk()) as pm:
        doc = pm.documents.add_bytes("notas.xyz", b"Primeira frase. Segunda frase.",
                                     owner="ana")["document"]
        assert doc["format"] == "xyz" and doc["chunks"] == 1
        hit = pm.documents.search("segunda frase", owner="ana")["results"][0]
        assert hit["citation"]["label"] == "notas.xyz, tudo"


def test_custom_prompts_are_used():
    class Prompts(PortuguesePrompts):
        def extraction(self, conversation):
            return "EXTRAIA: " + conversation[-1]["content"]

        def parse_extraction(self, raw):
            return [ExtractedFact(raw.strip())]

        def topics(self, facts, topics):
            return "ASSUNTOS"

        def parse_topics(self, raw, count, topics):
            return ["trabalho"] * count

    llm = ScriptedLLM(handler=lambda p: "O usuário é piloto" if p.startswith("EXTRAIA") else "")
    with make_pm(llm=llm, prompts=Prompts()) as pm:
        decision = pm.memories.add("sou piloto", owner="ana")["decisions"][0]
        assert decision == {"event": "add", "memory_id": decision["memory_id"],
                            "text": "O usuário é piloto", "previous_text": None,
                            "topic": "trabalho", "reason": None}


def test_reindex_moves_everything_to_the_new_embedder(tmp_path):
    path = tmp_path / "store.json"
    with PiMemory(embedder=FakeEmbedder(), llm=ScriptedLLM(), store=MemoryStore(path)) as pm:
        pm.memories.remember("O usuário mora em Cidade Exemplo", owner="ana")
        pm.documents.add_bytes("leia.txt", b"A senha do wifi fica na geladeira.",
                               owner="ana")
        result = pm.reindex(FakeEmbedder(dimension=32))
        assert result == {"memories": 1, "chunks": 1, "embedder": "fake:bow32"}
        assert pm.memories.search("Cidade Exemplo", owner="ana")["results"]
        assert pm.documents.search("wifi", owner="ana")["results"]

    with pytest.raises(EmbedderMismatchError):      # the old model no longer opens it
        PiMemory(embedder=FakeEmbedder(), llm=ScriptedLLM(), store=MemoryStore(path))
    with PiMemory(embedder=FakeEmbedder(dimension=32), llm=ScriptedLLM(),
                  store=MemoryStore(path)) as pm:
        assert pm.memories.list(owner="ana")["total"] == 1
        assert pm.documents.list(owner="ana")["documents"][0]["source"] == "leia.txt"
        pm.reindex(FakeEmbedder(dimension=16))      # a second reindex also works
        assert pm.memories.list(owner="ana")["total"] == 1
        assert pm.documents.search("wifi", owner="ana")["results"]


def test_from_config_builds_engines(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-ficticia-0123456789")
    pm = PiMemory.from_config({
        "embedder": {"type": "ollama", "model": "nomic-embed-text"},
        "llm": {"type": "gemini", "model": "gemini-3.5-flash"},
        "store": {"type": "memory"},
        "topics": ["trabalho", "outros"],
    }, embedder=FakeEmbedder())     # explicit objects still win (no Ollama needed here)
    assert type(pm.llm).__name__ == "GeminiLLM" and pm.topics == ("trabalho", "outros")
    assert type(pm.store).__name__ == "MemoryStore"


def test_from_config_refuses_keys_and_unknown_types():
    with pytest.raises(InvalidInputError, match="variável de ambiente"):
        PiMemory.from_config({"llm": {"type": "openai", "model": "x", "api_key": "sk-x"}})
    with pytest.raises(InvalidInputError, match="banana"):
        PiMemory.from_config({"store": {"type": "banana"}})


def test_public_modules_are_lazy():
    import subprocess
    import sys
    code = ("import sys, pi_memory.stores, pi_memory.llms, pi_memory.embedders; "
            "print(any(m.startswith(('qdrant_client', 'chromadb', 'fastembed')) "
            "for m in sys.modules))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.stdout.strip() == "False", out.stderr
    from pi_memory.llms import FunctionLLM
    from pi_memory.stores import MemoryStore as Store
    assert Store is MemoryStore and FunctionLLM(lambda p: "x").complete("y") == "x"
