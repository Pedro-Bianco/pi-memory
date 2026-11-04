"""MCP server over stdio (official SDK, extra `mcp`). Each operation of the table is a tool named
with "_" instead of "." (memories_add, documents_search, ...), with the same input schema; the
result is a text content with the same JSON as the Python API. Errors come back with isError and
the JSON {"error": {"code", "message"}}.

documents_add does not read files by path unless a folder is given (docs_dir): an agent may be
led by text it read ("prompt injection") to ask for a private file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from pi_memory import __version__
from pi_memory.engines._extras import require
from pi_memory.operations import OPERATIONS, dispatch, resolve

if TYPE_CHECKING:
    from pi_memory.client import PiMemory

INSTRUCTIONS = (
    "Memória de longo prazo e documentos de cada dono (owner). Use memories_search antes de "
    "responder sobre a pessoa (use as 3 primeiras), documents_search para perguntas sobre os "
    "documentos (cite citation.label) e memories_add com a troca de mensagens para aprender."
)


def tool_name(operation: str) -> str:
    return operation.replace(".", "_")


def make_server(pm: PiMemory, docs_dir: str | Path | None = None):
    require("mcp", "mcp", "O servidor MCP")
    from mcp import types
    from mcp.server.lowlevel import Server

    files = Path(docs_dir) if docs_dir is not None else False
    by_tool = {tool_name(name): name for name in OPERATIONS}
    tools = [types.Tool(name=tool_name(op.name), description=op.description,
                        input_schema=resolve(op.schema))
             for op in OPERATIONS.values()]

    async def on_list_tools(ctx, params):
        return types.ListToolsResult(tools=tools)

    async def on_call_tool(ctx, params):
        name = by_tool.get(params.name)
        result = (dispatch(pm, name, params.arguments or {}, files=files) if name else
                  {"error": {"code": "invalid_input",
                             "message": f"Ferramenta desconhecida: {params.name}"}})
        text = json.dumps(result, ensure_ascii=False)
        return types.CallToolResult(content=[types.TextContent(type="text", text=text)],
                                    is_error=isinstance(result.get("error"), dict))

    return Server("pi-memory", version=__version__, instructions=INSTRUCTIONS,
                  on_list_tools=on_list_tools, on_call_tool=on_call_tool)


def serve_stdio(pm: PiMemory, docs_dir: str | Path | None = None) -> None:
    import anyio
    from mcp.server.stdio import stdio_server

    server = make_server(pm, docs_dir)

    async def main():
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    anyio.run(main)
