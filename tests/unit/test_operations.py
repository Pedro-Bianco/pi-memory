"""The table of operations: input validation in Portuguese and errors as JSON, never exceptions."""

import base64

from pi_memory.operations import DEFS, OPERATIONS, dispatch, openapi, resolve
from tests.fakes import make_pm


def test_every_operation_has_a_schema_and_a_description():
    assert set(OPERATIONS) == set(DEFS["operations"])
    for op in OPERATIONS.values():
        assert op.description and "$ref" not in str(resolve(op.schema))


def test_validation_messages():
    pm = make_pm()
    cases = [
        ("memories.search", {"owner": "ana"}, "falta o campo 'query'"),
        ("memories.search", {"owner": "ana", "query": "x", "limit": 0}, "limit: mínimo 1"),
        ("memories.search", {"owner": "ana", "query": "x", "limt": 3}, "campo desconhecido 'limt'"),
        ("memories.add", {"owner": "ana", "messages": []}, "messages"),
        ("memories.add", {"owner": "ana", "messages": [{"role": "bot", "content": "x"}]},
         "messages"),
        ("documents.add", {"owner": "ana"}, "path ou filename + content_base64"),
        ("documents.add", {"owner": "ana", "path": "a.txt", "filename": "b.txt",
                           "content_base64": "eA=="}, "use exatamente uma das formas"),
        ("graph.data", {"owner": "ana", "include_documents": "sim"}, "boolean"),
        ("nada.disso", {}, "Operação desconhecida"),
    ]
    for name, params, fragment in cases:
        result = dispatch(pm, name, params)
        assert result["error"]["code"] == "invalid_input", (name, result)
        assert fragment in result["error"]["message"], (name, result["error"]["message"])
    assert dispatch(pm, "stats", ["não é objeto"])["error"]["code"] == "invalid_input"


def test_documents_add_by_content_and_bad_base64():
    pm = make_pm()
    data = base64.b64encode(b"Primeira frase. Segunda frase.").decode()
    ok = dispatch(pm, "documents.add", {"owner": "ana", "filename": "a.txt",
                                        "content_base64": data})
    assert ok["status"] == "added" and ok["document"]["collection"] == "geral"
    bad = dispatch(pm, "documents.add", {"owner": "ana", "filename": "a.txt",
                                         "content_base64": "@@@"})
    assert bad["error"]["code"] == "invalid_input"


def test_unexpected_errors_do_not_leak_internals():
    pm = make_pm()

    def boom(*args, **kwargs):
        raise RuntimeError("detalhe interno /caminho/secreto")

    pm.memories.search = boom
    result = dispatch(pm, "memories.search", {"owner": "ana", "query": "x"})
    assert result["error"]["code"] == "internal"
    assert "secreto" not in result["error"]["message"]


def test_openapi_lists_every_operation():
    paths = openapi("0.0.0")["paths"]
    assert set(paths) == {f"/v1/{name}" for name in OPERATIONS}
