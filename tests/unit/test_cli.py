"""Command line: one command per operation, JSON by default, readable text on request, exit
codes."""

import io
import json
from contextlib import redirect_stderr, redirect_stdout

import pytest

from pi_memory import cli
from pi_memory.operations import OPERATIONS
from tests.docs import FILES
from tests.fakes import ScriptedLLM, make_pm


@pytest.fixture
def pm(monkeypatch):
    instance = make_pm(llm=ScriptedLLM(handler=lambda p: "NULO"))
    instance.close = lambda: None
    monkeypatch.setattr(cli, "open_memory", lambda args: instance)
    return instance


def run(*argv, stdin=None, monkeypatch=None):
    out, err = io.StringIO(), io.StringIO()
    if stdin is not None:
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def test_every_operation_has_a_command():
    parser = cli.build_parser()
    for name in OPERATIONS:
        words = name.replace("_", "-").split(".")
        with pytest.raises(SystemExit) as info, redirect_stdout(io.StringIO()):
            parser.parse_args([*words, "--help"])
        assert info.value.code == 0, name


def test_json_by_default_and_text_on_request(pm):
    code, out, _ = run("memories", "remember", "--owner", "ana", "--text",
                       "O usuário gosta de jazz", "--topic", "lazer")
    assert code == 0 and json.loads(out)["topic"] == "lazer"
    code, out, _ = run("--format", "text", "memories", "list", "--owner", "ana")
    assert code == 0 and "1 memória(s)" in out and "[lazer] O usuário gosta de jazz" in out
    code, out, _ = run("--format", "text", "stats", "--owner", "ana")
    assert "memórias: 1 (lazer 1)" in out


def test_messages_as_plain_text_json_or_file(pm, tmp_path):
    assert json.loads(run("memories", "add", "--owner", "ana", "--messages", "oi tudo bem")[1]) == {
        "decisions": []}
    conversation = [{"role": "user", "content": "oi"}]
    assert run("memories", "add", "--owner", "ana", "--messages", json.dumps(conversation))[0] == 0
    path = tmp_path / "conversa.json"
    path.write_text(json.dumps(conversation), encoding="utf-8")
    assert run("memories", "add", "--owner", "ana", "--messages", f"@{path}")[0] == 0


def test_params_from_stdin_and_options_win(pm, monkeypatch):
    pm.memories.remember("O usuário gosta de jazz", "ana")
    pm.memories.remember("O usuário gosta de jazz", "bruno")
    code, out, _ = run("memories", "list", "--params", "-", "--owner", "ana",
                       stdin=json.dumps({"owner": "bruno", "limit": 5}), monkeypatch=monkeypatch)
    assert code == 0 and json.loads(out)["memories"][0]["owner"] == "ana"


def test_exit_codes_and_error_json(pm, tmp_path):
    code, out, err = run("memories", "get", "--owner", "ana", "--memory-id", "x")
    assert code == 3 and json.loads(out)["error"]["code"] == "not_found" and "não encontrada" in err
    code, out, _ = run("memories", "search", "--owner", "ana")
    assert code == 2 and json.loads(out)["error"]["code"] == "invalid_input"
    code, out, _ = run("memories", "nao-existe")
    assert code == 2 and "Uso inválido" in json.loads(out)["error"]["message"]
    scanned = tmp_path / "escaneado.txt"
    scanned.write_text("   ", encoding="utf-8")
    code, out, _ = run("documents", "add", "--owner", "ana", "--path", str(scanned))
    assert code == 6 and json.loads(out)["error"]["code"] == "no_text"


def test_documents_add_several_files_and_admin_commands(pm, tmp_path):
    paths = []
    for name in ("manual.txt", "notas.md"):
        (tmp_path / name).write_bytes(FILES[name])
        paths.append(str(tmp_path / name))
    code, out, _ = run("documents", "add", "--owner", "ana", "--collection", "casa",
                       "--path", *paths)
    assert code == 0 and [r["status"] for r in json.loads(out)["results"]] == ["added", "added"]
    code, out, _ = run("--format", "text", "collections", "list", "--owner", "ana")
    assert "- casa: 2 documento(s)" in out
    doc_id = next(d["id"] for d in pm.documents.list("ana")["documents"]
                  if d["source"] == "notas.md")                      # 3 chunks: one can go
    code, out, _ = run("--format", "text", "documents", "get", "--owner", "ana", "--doc-id", doc_id)
    assert code == 0 and "(casa)" in out
    chunk = json.loads(run("chunks", "list", "--owner", "ana", "--doc-id", doc_id,
                           "--limit", "1")[1])["chunks"][0]
    assert json.loads(run("chunks", "delete", "--owner", "ana", "--chunk-id", chunk["id"])[1]) == {
        "deleted": 1}
    code, out, _ = run("collections", "delete", "--owner", "ana", "--name", "casa")
    assert code == 0 and json.loads(out)["deleted_documents"] == 2


def test_text_document_and_graph_html(pm, tmp_path):
    code, out, _ = run("documents", "add-text", "--owner", "ana", "--title", "Wifi", "--text",
                       "A senha fica na geladeira.")
    assert code == 0 and json.loads(out)["document"]["source"] == "Wifi.md"
    code, out, _ = run("graph", "html", "--owner", "ana")
    assert code == 0 and out.lstrip().startswith("<!DOCTYPE html>")


def test_every_field_is_described_for_people_and_agents():
    """--help, the MCP tool schemas and OpenAPI all read these descriptions."""
    from pi_memory.operations import resolve

    for name, op in OPERATIONS.items():
        for prop, schema in resolve(op.schema)["properties"].items():
            assert schema.get("description"), f"{name}.{prop} sem descrição"


def test_help_shows_descriptions_defaults_and_examples():
    parser = cli.build_parser()
    out = io.StringIO()
    with pytest.raises(SystemExit), redirect_stdout(out):
        parser.parse_args(["memories", "search", "--help"])
    text = out.getvalue()
    assert "--query QUERY" in text and "OP:" not in text and "JSON:" not in text
    assert "Obrigatório" in text and "Padrão: 3" in text
    out = io.StringIO()
    with pytest.raises(SystemExit), redirect_stdout(out):
        parser.parse_args(["--help"])
    assert "exemplos:" in out.getvalue() and "3 não encontrado" in out.getvalue()


def test_schema_command(pm):
    code, out, _ = run("schema", "memories.search")
    data = json.loads(out)
    assert code == 0 and data["operation"] == "memories.search"
    assert data["input"]["required"] == ["query", "owner"]
    assert "description" in data["input"]["properties"]["owner"]
    code, out, _ = run("schema")
    assert code == 0 and set(json.loads(out)["operations"]) == set(OPERATIONS)
    code, out, _ = run("schema", "nada")
    assert code == 2 and json.loads(out)["error"]["code"] == "invalid_input"
