"""AsyncPiMemory: same results as the synchronous API, without blocking the event loop."""

import asyncio
import time

import pytest

from pi_memory import AsyncPiMemory, NotFoundError
from pi_memory.engines.stores.memory import MemoryStore
from tests.fakes import FakeEmbedder, ScriptedLLM


def make_async(**overrides):
    options = {"embedder": FakeEmbedder(), "store": MemoryStore(),
               "llm": ScriptedLLM(handler=lambda p: "FATO: O usuário gosta de jazz"
                                  if p.startswith("Abaixo") else "1. lazer")}
    options.update(overrides)
    return AsyncPiMemory(**options)


def test_same_operations_awaited():
    async def scenario():
        async with make_async() as pm:
            decisions = (await pm.memories.add("adoro jazz", owner="ana"))["decisions"]
            assert [d["event"] for d in decisions] == ["add"]
            assert (await pm.memories.search("jazz", owner="ana"))["results"][0]["text"] == (
                "O usuário gosta de jazz")
            doc = await pm.documents.add_text("Wifi", "A senha fica na geladeira.", owner="ana")
            assert doc["status"] == "added"
            assert (await pm.stats("ana"))["documents"] == 1
            graph = await pm.graph.data("ana", include_documents=True)
            assert {n["kind"] for n in graph["nodes"]} >= {"memory", "collection"}
            with pytest.raises(NotFoundError):
                await pm.memories.get("nao-existe", owner="ana")

    asyncio.run(scenario())


def test_event_loop_stays_free_and_calls_are_serialized():
    def slow(prompt):
        time.sleep(0.2)
        return "NULO"

    async def scenario():
        pm = make_async(llm=slow)
        ticks = 0

        async def heartbeat():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        beat = asyncio.create_task(heartbeat())
        started = time.perf_counter()
        await asyncio.gather(pm.memories.add("a", owner="ana"), pm.memories.add("b", owner="ana"))
        elapsed = time.perf_counter() - started
        beat.cancel()
        await pm.close()
        assert ticks >= 10            # the loop kept running while the model "thought"
        assert elapsed >= 0.4         # one call at a time (the stores are not thread-safe)

    asyncio.run(scenario())


def test_from_config():
    async def scenario():
        pm = AsyncPiMemory.from_config({"store": {"type": "memory"}}, embedder=FakeEmbedder(),
                                       llm=lambda p: "NULO")
        assert (await pm.memories.add("oi", owner="ana")) == {"decisions": []}
        await pm.close()

    asyncio.run(scenario())
