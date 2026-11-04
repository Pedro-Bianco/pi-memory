"""One table of operations shared by the command line, the HTTP server and the MCP server, so the
three speak exactly the same JSON as the Python API and none has rules of its own.

dispatch(pm, name, params) validates the input against the JSON Schema in schemas.json, calls the
library and returns the result dict, or {"error": {"code", "message"}}. It never raises.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

from pi_memory.errors import InvalidInputError, PiMemoryError

if TYPE_CHECKING:
    from pi_memory.client import PiMemory

SCHEMAS = json.loads(resources.files("pi_memory").joinpath("schemas.json").read_text("utf-8"))
DEFS = SCHEMAS["$defs"]


@dataclass(frozen=True)
class Operation:
    name: str
    description: str          # in Portuguese: shown to agents (MCP) and in --help
    run: Callable[[PiMemory, dict], object]

    @property
    def schema(self) -> dict:
        return DEFS["operations"][self.name]


def _add_document(pm: PiMemory, p: dict):
    if "path" in p:
        return pm.documents.add(p["path"], p["owner"], p.get("metadata"), p.get("collection"))
    try:
        data = base64.b64decode(p["content_base64"], validate=True)
    except (binascii.Error, ValueError):
        raise InvalidInputError("content_base64 não é base64 válido.") from None
    return pm.documents.add_bytes(p["filename"], data, p["owner"], p.get("metadata"),
                                  p.get("collection"))


OPERATIONS: dict[str, Operation] = {op.name: op for op in [
    Operation("memories.add",
              "Entrega uma conversa; extrai fatos sobre o dono e decide guardar, substituir, "
              "apagar ou ignorar cada um. Devolve as decisões.",
              lambda pm, p: pm.memories.add(p["messages"], p["owner"], p.get("metadata"))),
    Operation("memories.remember", "Guarda um fato diretamente, sem passar pelo modelo.",
              lambda pm, p: pm.memories.remember(p["text"], p["owner"], p.get("topic"),
                                                 p.get("metadata"))),
    Operation("memories.search",
              "Busca memórias do dono por significado e palavra exata; use as 3 primeiras.",
              lambda pm, p: pm.memories.search(p["query"], p["owner"], p.get("limit", 3),
                                               p.get("filters"))),
    Operation("memories.get", "Uma memória pelo id.",
              lambda pm, p: pm.memories.get(p["memory_id"], p["owner"])),
    Operation("memories.list", "Lista as memórias do dono, mais recentes primeiro.",
              lambda pm, p: pm.memories.list(p["owner"], p.get("topic"), p.get("limit", 100),
                                             p.get("offset", 0))),
    Operation("memories.update", "Edita texto, assunto ou metadados de uma memória.",
              lambda pm, p: pm.memories.update(p["memory_id"], p["owner"], p.get("text"),
                                               p.get("topic"), p.get("metadata"))),
    Operation("memories.delete", "Apaga uma memória.",
              lambda pm, p: pm.memories.delete(p["memory_id"], p["owner"])),
    Operation("memories.delete_all", "Apaga todas as memórias do dono.",
              lambda pm, p: pm.memories.delete_all(p["owner"])),
    Operation("documents.add",
              "Adiciona um documento (PDF, Word, planilha, apresentação, texto) numa coleção, por "
              "caminho (path) ou conteúdo (filename + content_base64).", _add_document),
    Operation("documents.add_text", "Cria um documento a partir de um texto digitado.",
              lambda pm, p: pm.documents.add_text(p["title"], p["text"], p["owner"],
                                                  p.get("collection"), p.get("metadata"))),
    Operation("documents.get", "Um documento com todos os seus trechos.",
              lambda pm, p: pm.documents.get(p["doc_id"], p["owner"])),
    Operation("documents.search",
              "Pesquisa nos documentos do dono; cada trecho vem com a citação de onde veio.",
              lambda pm, p: pm.documents.search(p["query"], p["owner"], p.get("limit", 5),
                                                p.get("filters"), p.get("collection"))),
    Operation("documents.list", "Lista os documentos do dono (de uma coleção, se indicada).",
              lambda pm, p: pm.documents.list(p["owner"], p.get("collection"))),
    Operation("documents.remove", "Remove um documento e todos os seus trechos.",
              lambda pm, p: pm.documents.remove(p["doc_id"], p["owner"])),
    Operation("collections.list", "Coleções do dono com o número de documentos e trechos.",
              lambda pm, p: pm.documents.collections(p["owner"])),
    Operation("collections.delete", "Apaga uma coleção inteira (documentos e trechos).",
              lambda pm, p: pm.documents.delete_collection(p["name"], p["owner"])),
    Operation("chunks.list", "Lista trechos guardados (de um documento ou coleção).",
              lambda pm, p: pm.documents.chunks(p["owner"], p.get("doc_id"),
                                                p.get("collection"), p.get("limit", 50),
                                                p.get("offset", 0))),
    Operation("chunks.get", "Um trecho pelo id.",
              lambda pm, p: pm.documents.chunk(p["chunk_id"], p["owner"])),
    Operation("chunks.delete", "Apaga um trecho.",
              lambda pm, p: pm.documents.delete_chunk(p["chunk_id"], p["owner"])),
    Operation("graph.data",
              "Grafo do dono: memórias por assunto e, com include_documents, a base de "
              "conhecimento (coleções, documentos e, com include_chunks, trechos).",
              lambda pm, p: pm.graph.data(p["owner"], p.get("include_documents", False),
                                          p.get("include_chunks", False))),
    Operation("graph.html", "Página HTML interativa do grafo, como texto.",
              lambda pm, p: {"html": pm.graph.html(p["owner"], None,
                                                   p.get("include_documents", True),
                                                   p.get("include_chunks", False))}),
    Operation("stats", "Visão geral do dono: memórias por assunto, coleções, documentos, "
                       "trechos e motores em uso.",
              lambda pm, p: pm.stats(p["owner"])),
]}


# ── JSON Schema (the subset schemas.json uses) ──────────────────────────────────────────────
_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "object": dict,
          "array": list, "null": type(None)}


def resolve(schema: dict) -> dict:
    """The schema with every $ref inlined (MCP clients need self-contained schemas)."""
    if isinstance(schema, dict):
        if "$ref" in schema:
            siblings = {k: resolve(v) for k, v in schema.items() if k != "$ref"}
            return {**resolve(DEFS[schema["$ref"].split("/")[-1]]), **siblings}
        return {k: resolve(v) for k, v in schema.items()}
    if isinstance(schema, list):
        return [resolve(v) for v in schema]
    return schema


def _type_ok(value, expected) -> bool:
    names = expected if isinstance(expected, list) else [expected]
    for name in names:
        if name in ("integer", "number") and isinstance(value, bool):
            continue
        if isinstance(value, _TYPES[name]):
            return True
    return False


def _errors(value, schema: dict, where: str) -> list[str]:
    schema = resolve(schema)
    if "oneOf" in schema:
        matching = [s for s in schema["oneOf"] if not _errors(value, s, where)]
        if len(matching) != 1:
            forms = [" + ".join(s["required"]) if "required" in s else f"um {s.get('type')}"
                     for s in schema["oneOf"]]
            return [f"{where}: use exatamente uma das formas: {' ou '.join(forms)}"]
    if "type" in schema and not _type_ok(value, schema["type"]):
        return [f"{where}: tipo esperado {schema['type']}"]
    problems = []
    if "enum" in schema and value not in schema["enum"]:
        problems.append(f"{where}: valor deve ser um de {schema['enum']}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            problems.append(f"{where}: não pode ser vazio")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            problems.append(f"{where}: no máximo {schema['maxLength']} caracteres")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            problems.append(f"{where}: mínimo {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            problems.append(f"{where}: máximo {schema['maximum']}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            problems.append(f"{where}: lista vazia")
        for i, item in enumerate(value):
            problems += _errors(item, schema.get("items", {}), f"{where}[{i}]")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                problems.append(f"falta o campo '{key}'" if where == "entrada"
                                else f"{where}: falta '{key}'")
        properties = schema.get("properties")
        for key, item in value.items():
            if properties is not None and key in properties:
                problems += _errors(item, properties[key], key if where == "entrada"
                                    else f"{where}.{key}")
            elif properties is not None and "additionalProperties" not in schema:
                problems.append(f"campo desconhecido '{key}'")
            elif isinstance(schema.get("additionalProperties"), dict):
                problems += _errors(item, schema["additionalProperties"], f"{where}.{key}")
    return problems


def validate(name: str, params) -> dict:
    if name not in OPERATIONS:
        raise InvalidInputError(f"Operação desconhecida: '{name}'. Existem: "
                                f"{', '.join(OPERATIONS)}.")
    if not isinstance(params, dict):
        raise InvalidInputError("Os parâmetros precisam ser um objeto JSON.")
    problems = _errors(params, OPERATIONS[name].schema, "entrada")
    if problems:
        raise InvalidInputError(f"Entrada inválida para {name}: " + "; ".join(problems) + ".")
    return params


def allowed_path(path: str, files: bool | Path) -> str:
    """Where documents.add may read a file from a path given by the caller.
    True: anywhere (command line, run by the user herself). False: nowhere (servers by default:
    a remote client or an agent obeying an injected instruction must not read this machine's
    files). A folder: only inside it, after resolving "..", links and relative paths."""
    if files is True:
        return path
    if files is False:
        raise InvalidInputError(
            "Este servidor não lê arquivos pelo caminho (path). Envie filename + content_base64, "
            "ou inicie o servidor com --docs-dir PASTA para liberar só aquela pasta.")
    root = Path(files).resolve()
    target = (root / path).resolve()
    try:
        inside = os.path.commonpath([os.path.normcase(root), os.path.normcase(target)]) == \
            os.path.normcase(root)
    except ValueError:                            # Windows: another drive
        inside = False
    if not inside:
        raise InvalidInputError(f"O caminho precisa estar dentro da pasta liberada ({root}).")
    return str(target)


def dispatch(pm: PiMemory, name: str, params, *, files: bool | Path = False) -> dict:
    """files: where documents.add may read paths from (see allowed_path); servers keep the
    default False, the command line passes True."""
    try:
        params = validate(name, params)          # checks the name first
        if name == "documents.add" and "path" in params:
            params = {**params, "path": allowed_path(params["path"], files)}
        result = OPERATIONS[name].run(pm, params)
        return result if isinstance(result, dict) else {"result": result}
    except PiMemoryError as e:
        return e.to_dict()
    except Exception as e:   # unexpected: no stack trace or internals to the client
        return {"error": {"code": "internal",
                          "message": f"Erro interno ({type(e).__name__}). Veja o terminal do "
                                     "servidor ou rode a mesma operação pela biblioteca."}}


def openapi(version: str) -> dict:
    paths = {}
    for op in OPERATIONS.values():
        paths[f"/v1/{op.name}"] = {"post": {
            "summary": op.description, "operationId": op.name.replace(".", "_"),
            "requestBody": {"required": True, "content": {
                "application/json": {"schema": resolve(op.schema)}}},
            "responses": {"200": {"description": "resultado da operação (JSON)"},
                          "4XX": {"description": "erro: {\"error\": {\"code\", \"message\"}}"},
                          "5XX": {"description": "erro: {\"error\": {\"code\", \"message\"}}"}}}}
    return {"openapi": "3.1.0",
            "info": {"title": "pi-memory", "version": version,
                     "description": "Memória de longo prazo, documentos e grafo."},
            "paths": paths}
