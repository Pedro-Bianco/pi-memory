"""AsyncPiMemory: the same API for asyncio applications (FastAPI, async agents).

Every call runs the synchronous library in a worker thread (asyncio.to_thread), so the event loop
is never blocked by embeddings, the language model or the store. Calls run one at a time: the
local stores are not meant for concurrent use from several threads.
"""

from __future__ import annotations

import asyncio
import functools
from typing import Any

from pi_memory.client import PiMemory


class _AsyncSection:
    """Async view of pm.memories, pm.documents or pm.graph: same methods, awaited."""

    def __init__(self, owner: AsyncPiMemory, name: str):
        self._owner = owner
        self._name = name

    def __getattr__(self, method: str):
        target = getattr(getattr(self._owner.sync, self._name), method)
        if not callable(target):
            return target

        @functools.wraps(target)
        async def call(*args, **kwargs):
            return await self._owner._run(target, *args, **kwargs)

        return call


class AsyncPiMemory:
    """Same constructor as PiMemory; `await` every operation.

        async with AsyncPiMemory(path="memoria") as pm:
            await pm.memories.add("me mudei para Recife", owner="ana")
            hits = await pm.documents.search("prazo", owner="ana")
    """

    def __init__(self, *args, **kwargs):
        self.sync = PiMemory(*args, **kwargs)
        self._lock = asyncio.Lock()
        self.memories = _AsyncSection(self, "memories")
        self.documents = _AsyncSection(self, "documents")
        self.graph = _AsyncSection(self, "graph")

    @classmethod
    def from_config(cls, settings: dict, **overrides) -> AsyncPiMemory:
        instance = cls.__new__(cls)
        instance.sync = PiMemory.from_config(settings, **overrides)
        instance._lock = asyncio.Lock()
        instance.memories = _AsyncSection(instance, "memories")
        instance.documents = _AsyncSection(instance, "documents")
        instance.graph = _AsyncSection(instance, "graph")
        return instance

    async def _run(self, fn, *args, **kwargs) -> Any:
        async with self._lock:
            return await asyncio.to_thread(fn, *args, **kwargs)

    async def stats(self, owner: str) -> dict:
        return await self._run(self.sync.stats, owner)

    async def reindex(self, new_embedder) -> dict:
        return await self._run(self.sync.reindex, new_embedder)

    async def close(self) -> None:
        await self._run(self.sync.close)

    async def __aenter__(self) -> AsyncPiMemory:
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()
