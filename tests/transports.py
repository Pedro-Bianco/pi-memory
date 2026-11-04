"""Run a sequence of operations through each transport (library dispatch, HTTP, MCP, command
line) against a given PiMemory and return the JSON results, so contract tests can compare them."""

import io
import json
import threading
import urllib.error
import urllib.request
from contextlib import redirect_stdout

from pi_memory import cli
from pi_memory.operations import dispatch
from pi_memory.servers.http import make_server


def via_dispatch(pm, sequence):
    return [dispatch(pm, name, params) for name, params in sequence]


def via_http(pm, sequence):
    server = make_server(pm, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/v1/"
    results = []
    try:
        for name, params in sequence:
            request = urllib.request.Request(base + name, data=json.dumps(params).encode(),
                                             headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(request) as response:
                    results.append(json.loads(response.read()))
            except urllib.error.HTTPError as e:
                results.append(json.loads(e.read()))
    finally:
        server.shutdown()
        server.server_close()
    return results


def via_mcp(pm, sequence):
    import anyio
    from mcp.client import Client

    from pi_memory.servers.mcp import make_server as make_mcp
    from pi_memory.servers.mcp import tool_name

    results = []

    async def run():
        async with Client(make_mcp(pm)) as client:
            for name, params in sequence:
                answer = await client.call_tool(tool_name(name), params)
                payload = json.loads(answer.content[0].text)
                assert answer.is_error == ("error" in payload)
                results.append(payload)

    anyio.run(run)
    return results


def via_cli(monkeypatch, pm, sequence):
    close = pm.close
    pm.close = lambda: None                       # the CLI closes after each command
    monkeypatch.setattr(cli, "open_memory", lambda args: pm)
    results = []
    try:
        for name, params in sequence:
            words = name.replace("_", "-").split(".")
            out = io.StringIO()
            with redirect_stdout(out):
                cli.main([*words, "--params", json.dumps(params)])
            text = out.getvalue()
            if name == "graph.html" and not text.lstrip().startswith("{"):
                results.append({"html": text})        # the CLI prints the page itself
            else:
                results.append(json.loads(text))
    finally:
        pm.close = close
    return results
