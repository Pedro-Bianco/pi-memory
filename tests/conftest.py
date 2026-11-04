import pytest

from pi_memory.engines.stores.memory import MemoryStore
from tests.fakes import FakeEmbedder, ScriptedLLM, make_pm


@pytest.fixture
def llm():
    return ScriptedLLM()


@pytest.fixture
def store():
    return MemoryStore()


@pytest.fixture
def pm(llm, store):
    with make_pm(llm=llm, store=store, embedder=FakeEmbedder()) as instance:
        yield instance
