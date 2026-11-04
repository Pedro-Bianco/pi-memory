"""The same operations through the library (dispatch), HTTP, MCP and the command line give the
same JSON: one table of operations, no rules of their own in the transports."""

import base64
import importlib.util
import re

import pytest

from pi_memory.operations import OPERATIONS
from tests.fakes import ScriptedLLM, make_pm
from tests.transports import via_cli, via_dispatch, via_http, via_mcp
from tests.unit.test_memories import router

NOTES = base64.b64encode("# Ata\n\nA reunião de março aprovou o orçamento.".encode()).decode()
SEQUENCE = [
    ("memories.remember", {"text": "O usuário gosta de jazz", "owner": "ana", "topic": "lazer"}),
    ("memories.add", {"messages": "me mudei para Recife", "owner": "ana"}),
    ("memories.search", {"query": "jazz", "owner": "ana"}),
    ("memories.list", {"owner": "ana"}),
    ("documents.add", {"filename": "ata.md", "content_base64": NOTES, "owner": "ana",
                       "collection": "atas"}),
    ("documents.add_text", {"title": "Wifi", "text": "A senha fica na geladeira.",
                            "owner": "ana"}),
    ("collections.list", {"owner": "ana"}),
    ("documents.search", {"query": "senha do wifi", "owner": "ana"}),
    ("chunks.list", {"owner": "ana"}),
    ("stats", {"owner": "ana"}),
    ("graph.data", {"owner": "ana", "include_documents": True}),
    ("memories.get", {"memory_id": "nao-existe", "owner": "ana"}),
    ("memories.search", {"query": "", "owner": "ana", "extra": 1}),
    ("collections.delete", {"name": "atas", "owner": "ana"}),
    ("documents.list", {"owner": "ana"}),
]
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\b[0-9a-f]{16}\b")
STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z")


def fresh_pm():
    llm = ScriptedLLM(handler=router(extraction="FATO: O usuário mora em Recife",
                                     topics="1. casa", decisions=["ADD"] * 5))
    return make_pm(llm=llm)


def normalize(value):
    """ids and timestamps differ between runs; everything else must be identical."""
    if isinstance(value, dict):
        result = {k: normalize(v) for k, v in sorted(value.items())}
        if isinstance(result.get("memories"), list):
            # memories saved in the same clock tick tie on updated_at: their order is not part
            # of the contract (seen on Windows, where the two runs had different timings)
            result["memories"].sort(key=lambda m: m["text"])
        return result
    if isinstance(value, list):
        return [normalize(v) for v in value]
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, str):
        return STAMP.sub("<data>", UUID.sub("<id>", value))
    return value


def test_every_operation_is_exercised():
    used = {name for name, _ in SEQUENCE}
    assert used >= set(OPERATIONS) - {"memories.update", "memories.delete", "memories.delete_all",
                                       "documents.get", "documents.remove", "chunks.get",
                                       "chunks.delete", "graph.html"}


def test_http_and_cli_match_the_library(monkeypatch):
    expected = normalize(via_dispatch(fresh_pm(), SEQUENCE))
    assert expected[11]["error"]["code"] == "not_found"
    assert expected[12]["error"]["code"] == "invalid_input"
    assert normalize(via_http(fresh_pm(), SEQUENCE)) == expected
    assert normalize(via_cli(monkeypatch, fresh_pm(), SEQUENCE)) == expected


@pytest.mark.skipif(not importlib.util.find_spec("mcp"), reason="extra mcp não instalado")
def test_mcp_matches_the_library():
    assert normalize(via_mcp(fresh_pm(), SEQUENCE)) == normalize(via_dispatch(fresh_pm(), SEQUENCE))
