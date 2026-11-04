"""Command line `pi-memory` (docs/GUIA.md, section 12.5). One subcommand per operation of the
table in operations.py, so the output is the same JSON as the library, HTTP and MCP; errors go to
stdout as JSON and to stderr as a message, with an exit code per kind."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import sys
from pathlib import Path

from pi_memory import PiMemory, __version__
from pi_memory.errors import InvalidInputError, PiMemoryError
from pi_memory.operations import OPERATIONS, dispatch, resolve

MIN_TOKEN = 16      # characters; a short token can be guessed by trying

EXIT_CODES = {
    "invalid_input": 2, "not_found": 3, "engine_unavailable": 4, "engine_timeout": 4,
    "engine_auth": 4, "engine_response": 4, "embedder_mismatch": 5, "store_busy": 5,
    "unsupported_format": 6, "no_text": 6, "unreadable_document": 6, "missing_extra": 7,
}


class _Parser(argparse.ArgumentParser):
    """Usage errors become the same JSON error (code invalid_input, exit 2) as everything else."""

    def error(self, message: str):
        raise InvalidInputError(f"Uso inválido: {message}. Veja: pi-memory --help")


def _utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def _option(prop: str) -> str:
    return "--" + prop.replace("_", "-")


def _accepts(schema: dict, kind: str) -> bool:
    if "oneOf" in schema:
        return any(_accepts(s, kind) for s in schema["oneOf"])
    types = schema.get("type")
    return kind in (types if isinstance(types, list) else [types])


def _json_value(text: str, schema: dict, prop: str):
    """Objects and lists: JSON inline or @file.json; plain text when the schema accepts text."""
    if text.startswith("@"):
        try:
            return json.loads(_read(text[1:], _option(prop)))
        except ValueError as e:
            raise InvalidInputError(f"{_option(prop)}: não consegui ler '{text[1:]}': {e}") \
                from None
    try:
        return json.loads(text)
    except ValueError:
        if _accepts(schema, "string"):
            return text
        raise InvalidInputError(f"{_option(prop)} precisa ser JSON (ou @arquivo.json).") from None


def _help(notes: list[str]) -> str:
    """"Descrição. Obrigatório. Padrão: 3." (argparse needs % doubled)."""
    parts = [n.rstrip(".") for n in notes if n]
    return ". ".join(p[0].upper() + p[1:] for p in parts).replace("%", "%%") + "."


EPILOG = """exemplos:
  pi-memory memories remember --owner ana --text "O usuário tem uma gata" --topic animais
  pi-memory memories search --owner ana --query "que animal a Ana tem?"
  pi-memory memories add --params '{"owner": "ana", "messages": "me mudei para Recife"}'
  pi-memory documents add --owner ana --collection contratos --path contrato.pdf
  pi-memory schema memories.search          # esquema JSON dos parâmetros

saída: JSON na saída padrão (--format text para pessoas). Em erro, {"error": {"code",
"message"}} na saída padrão, a mensagem na saída de erro e o código de saída:
  0 ok · 2 entrada inválida · 3 não encontrado · 4 motor (Ollama, nuvem) · 5 embedding
  diferente ou pasta em uso · 6 documento ilegível · 7 extra não instalado · 1 outros
"""

GROUPS = {"memories": "memórias", "documents": "documentos",
          "collections": "coleções da base de conhecimento", "chunks": "trechos guardados",
          "graph": "grafo"}


def _add_operation(commands, groups: dict, name: str) -> None:
    operation = OPERATIONS[name]
    if "." in name:
        group, action = name.split(".")
        parent = groups[group]
    else:
        parent, action = commands, name
    sub = parent.add_parser(action.replace("_", "-"), help=operation.description,
                            description=operation.description)
    sub.set_defaults(operation=name)
    schema = resolve(operation.schema)
    required = set(schema.get("required", []))
    for prop, prop_schema in schema["properties"].items():
        flag = _option(prop)
        notes = [prop_schema.get("description", "")]
        if prop in required:
            notes.append("obrigatório")
        if "default" in prop_schema:
            notes.append(f"padrão: {json.dumps(prop_schema['default'])}")
        metavar = prop.upper()
        if name == "documents.add" and prop == "path":
            sub.add_argument(flag, dest="file_paths", nargs="+", default=argparse.SUPPRESS,
                             metavar="ARQUIVO", help="Um ou mais arquivos (PDF, .docx, .xlsx, "
                                                     ".csv, .pptx, .txt, .md).")
        elif _accepts(prop_schema, "integer") and not _accepts(prop_schema, "string"):
            sub.add_argument(flag, dest=f"op:{prop}", type=int, default=argparse.SUPPRESS,
                             metavar="N", help=_help(notes))
        elif prop_schema.get("type") == "string" and "oneOf" not in prop_schema:
            sub.add_argument(flag, dest=f"op:{prop}", default=argparse.SUPPRESS, metavar=metavar,
                             help=_help(notes))
        else:
            notes.insert(1, "JSON ou @arquivo.json")
            sub.add_argument(flag, dest=f"json:{prop}", default=argparse.SUPPRESS,
                             metavar=metavar, help=_help(notes))
    sub.add_argument("--params", default=None, metavar="JSON",
                     help="Todos os parâmetros num objeto JSON (o mesmo do HTTP e do MCP), "
                          "@arquivo.json ou - para ler da entrada padrão; as opções acima têm "
                          "precedência.")
    if name == "graph.html":
        sub.add_argument("--out", default=None, help="arquivo; sem ele o HTML vai para a saída")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="pi-memory", description="Memória de longo prazo, documentos e grafo.",
                     epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--path", dest="data_path", default=os.environ.get("PI_MEMORY_PATH"),
                        help="pasta do banco local (padrão: pi_memory_data)")
    parser.add_argument("--config", default=os.environ.get("PI_MEMORY_CONFIG"),
                        help="arquivo JSON com a escolha de motores")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--pretty", action="store_true", help="JSON indentado")
    parser.add_argument("--version", action="version", version=f"pi-memory {__version__}")
    commands = parser.add_subparsers(dest="group", required=True, parser_class=_Parser)
    groups = {group: commands.add_parser(group, help=label).add_subparsers(
                  dest="action", required=True, parser_class=_Parser)
              for group, label in GROUPS.items()}
    for name in OPERATIONS:
        _add_operation(commands, groups, name)
    schema = commands.add_parser("schema", help="esquema JSON dos parâmetros de uma operação "
                                                "(ou de todas), para agentes e scripts")
    schema.add_argument("operation_name", nargs="?", metavar="OPERAÇÃO",
                        help=f"uma de: {', '.join(OPERATIONS)}")
    http = commands.add_parser("serve-http", help="servidor HTTP (mesmo JSON)")
    http.add_argument("--host", default="127.0.0.1")
    http.add_argument("--port", type=int, default=8765)
    http.add_argument("--token", default=None,
                      help="exige 'Authorization: Bearer <token>'; prefira a variável "
                           "PI_MEMORY_TOKEN (o que se digita na linha de comando fica no "
                           "histórico e na lista de processos)")
    mcp = commands.add_parser("serve-mcp", help="servidor MCP por stdio")
    for server in (http, mcp):
        server.add_argument("--docs-dir", default=None,
                            help="única pasta de onde documents.add pode ler arquivos pelo "
                                 "caminho (padrão: nenhuma; envie o conteúdo em base64)")
    return parser


def _read(path: str, what: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise InvalidInputError(f"Não consegui ler {what} '{path}': {e}") from None


def _docs_dir(args) -> Path | None:
    if args.docs_dir is None:
        return None
    folder = Path(args.docs_dir)
    if not folder.is_dir():
        raise InvalidInputError(f"--docs-dir: a pasta '{folder}' não existe.")
    return folder.resolve()


def open_memory(args) -> PiMemory:
    settings: dict = {}
    if args.config:
        try:
            settings = json.loads(_read(args.config, "a configuração"))
        except ValueError as e:
            raise InvalidInputError(f"Não consegui ler a configuração '{args.config}': {e}") \
                from None
    if args.data_path:
        settings["path"] = args.data_path
    return PiMemory.from_config(settings)


def collect_params(args) -> dict:
    """--params first, then each option (options win)."""
    params: dict = {}
    if args.params:
        if args.params == "-":
            source = sys.stdin.read()
        elif args.params.startswith("@"):
            source = _read(args.params[1:], "--params")
        else:
            source = args.params
        try:
            params = json.loads(source)
        except ValueError:
            raise InvalidInputError("--params precisa ser um objeto JSON.") from None
        if not isinstance(params, dict):
            raise InvalidInputError("--params precisa ser um objeto JSON.")
    schema = resolve(OPERATIONS[args.operation].schema)["properties"]
    for key, value in vars(args).items():
        if key.startswith("op:"):
            params[key[3:]] = value
        elif key.startswith("json:"):
            params[key[5:]] = _json_value(value, schema[key[5:]], key[5:])
    if hasattr(args, "file_paths"):
        params["path"] = args.file_paths
    return params


# ── text output (people only; scripts use the default JSON) ────────────────────────────────
def as_text(result) -> str:
    if not isinstance(result, dict):
        return str(result)
    if "error" in result:
        return f"erro {result['error']['code']}: {result['error']['message']}"
    if "engines" in result and "memories" in result:
        m = result["memories"]
        topics = ", ".join(f"{k} {v}" for k, v in m["by_topic"].items()) or "nenhum"
        lines = [f"dono: {result['owner']}",
                 f"memórias: {m['total']} ({topics})",
                 f"coleções: {len(result['collections'])} · documentos: {result['documents']} · "
                 f"trechos: {result['chunks']}"]
        lines += [f"  - {c['name']}: {c['documents']} documento(s), {c['chunks']} trecho(s)"
                  for c in result["collections"]]
        e = result["engines"]
        lines.append(f"motores: {e['embedder']} ({e['dimension']} dim.), {e['store']}, {e['llm']}")
        return "\n".join(lines)
    if "collections" in result:
        rows = [f"- {c['name']}: {c['documents']} documento(s), {c['chunks']} trecho(s)"
                for c in result["collections"]]
        return "\n".join(rows) or "nenhuma coleção"
    if "chunks" in result and isinstance(result["chunks"], list):
        header = (f"{result['document']['source']} ({result['document']['collection']})"
                  if "document" in result else f"{result.get('total', 0)} trecho(s)")
        rows = [f"- [{c['location']}] {c['text'][:100]}  ({c['id']})" for c in result["chunks"]]
        return "\n".join([header, *rows])
    if "deleted_documents" in result:
        return (f"coleção apagada: {result['deleted_documents']} documento(s), "
                f"{result['deleted_chunks']} trecho(s)")
    if "location" in result and "doc_id" in result:
        where = f"{result['source']}, {result['location']} ({result['collection']})"
        return f"{where}\n{result['text']}"
    if "decisions" in result:
        if not result["decisions"]:
            return "nada a guardar"
        lines = []
        for d in result["decisions"]:
            before = f"  (antes: {d['previous_text']})" if d.get("previous_text") else ""
            reason = f"  [{d['reason']}]" if d.get("reason") else ""
            lines.append(f"{d['event']:<7} {d['text']}{before}{reason}")
        return "\n".join(lines)
    if "results" in result:
        lines = []
        for r in result["results"]:
            if "score" not in r:
                lines.append(as_text(r))
                continue
            where = r["citation"]["label"] if "citation" in r else f"[{r['memory']['topic']}]"
            lines.append(f"{r['score']:6.3f}  {where}  {r['text']}")
        return "\n".join(lines) or "nenhum resultado"
    if "memories" in result:
        rows = [f"- [{m['topic']}] {m['text']}  ({m['id']})" for m in result["memories"]]
        return "\n".join([f"{result['total']} memória(s)", *rows])
    if "documents" in result:
        rows = [f"- {d['collection']}/{d['source']}  {d['format']}  {d['chunks']} trecho(s)  "
                f"({d['id']})" for d in result["documents"]]
        return "\n".join(rows) or "nenhum documento"
    if "status" in result and "document" in result:
        d = result["document"]
        return f"{result['status']}: {d['source']} ({d['chunks']} trecho(s), id {d['id']})"
    if "nodes" in result:
        topics = sum(1 for n in result["nodes"] if n["kind"] == "topic")
        return (f"{len(result['nodes']) - topics} memória(s), {topics} assunto(s), "
                f"{len(result['edges'])} ligação(ões)")
    if "id" in result and "text" in result:
        return f"[{result.get('topic')}] {result['text']}  ({result['id']})"
    return "\n".join(f"{k}: {v}" for k, v in result.items())


def schemas(name: str | None) -> dict:
    if name is None:
        return {"operations": {n: {"description": op.description, "input": resolve(op.schema)}
                               for n, op in OPERATIONS.items()}}
    if name not in OPERATIONS:
        raise InvalidInputError(f"Operação desconhecida: '{name}'. Existem: "
                                f"{', '.join(OPERATIONS)}.")
    return {"operation": name, "description": OPERATIONS[name].description,
            "input": resolve(OPERATIONS[name].schema)}


def run(args):
    if args.group == "schema":
        return schemas(args.operation_name)
    if args.group == "serve-http":
        return serve_http(args)
    if args.group == "serve-mcp":
        from pi_memory.servers.mcp import serve_stdio
        folder = _docs_dir(args)
        with open_memory(args) as pm:
            serve_stdio(pm, folder)
        return None
    params = collect_params(args)
    with open_memory(args) as pm:
        if args.operation == "documents.add" and isinstance(params.get("path"), list):
            paths = params.pop("path")
            results = [dispatch(pm, "documents.add", {**params, "path": p}, files=True)
                       for p in paths]
            return results[0] if len(results) == 1 else {"results": results}
        # the command line is run by the user herself: her own files are allowed
        result = dispatch(pm, args.operation, params, files=True)
    if args.operation == "graph.html" and "html" in result:
        if args.out:
            try:
                Path(args.out).write_text(result["html"], encoding="utf-8")
            except OSError as e:
                raise InvalidInputError(f"Não consegui gravar '{args.out}': {e}") from None
            return {"path": args.out}
        return result["html"]
    return result


def serve_http(args):
    from pi_memory.servers.http import make_server
    if args.token is not None:
        print("Aviso: o token digitado na linha de comando fica no histórico e na lista de "
              "processos; prefira a variável PI_MEMORY_TOKEN.", file=sys.stderr)
    else:
        args.token = os.environ.get("PI_MEMORY_TOKEN") or None
    if args.token is not None and len(args.token) < MIN_TOKEN:
        raise InvalidInputError(
            f"Token curto demais (mínimo {MIN_TOKEN} caracteres). Gere um com: python -c "
            '"import secrets; print(secrets.token_urlsafe(32))"')
    folder = _docs_dir(args)
    try:
        loopback = ipaddress.ip_address(args.host).is_loopback
    except ValueError:
        loopback = args.host == "localhost"
    if not loopback and not args.token:
        raise InvalidInputError(
            f"Recusado: ouvir em {args.host} expõe a memória fora desta máquina. Defina um token "
            "(--token ou PI_MEMORY_TOKEN) e use HTTPS na frente do servidor.")
    with open_memory(args) as pm:
        server = make_server(pm, args.host, args.port, args.token, folder)
        print(f"pi-memory em http://{args.host}:{server.server_address[1]}/ "
              f"({'com token' if args.token else 'sem token'}"
              f"{f'; arquivos só de {folder}' if folder else ''}; Ctrl+C para parar)",
              file=sys.stderr)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    return None


def _error_code(result) -> str | None:
    if not isinstance(result, dict):
        return None
    if isinstance(result.get("error"), dict):
        return result["error"].get("code")
    for item in result.get("results", []):
        if isinstance(item, dict) and isinstance(item.get("error"), dict):
            return item["error"].get("code")
    return None


def main(argv: list[str] | None = None) -> int:
    _utf8_console()
    try:
        args = build_parser().parse_args(argv)
        result = run(args)
    except PiMemoryError as e:
        print(json.dumps(e.to_dict(), ensure_ascii=False))
        print(e.message, file=sys.stderr)
        return EXIT_CODES.get(e.code, 1)
    if result is None:
        return 0
    if isinstance(result, str):
        sys.stdout.write(result)
        return 0
    if args.format == "text":
        print(as_text(result))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    code = _error_code(result)
    if code:
        if isinstance(result.get("error"), dict):
            print(result["error"]["message"], file=sys.stderr)
        return EXIT_CODES.get(code, 1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
