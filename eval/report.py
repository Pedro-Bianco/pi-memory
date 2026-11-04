"""Builds the "Resultados medidos" tables of the README from eval/results/*.json, so no number
in the README is typed by hand (rule: measure before claiming).

    python eval/report.py            # prints the Markdown
    python eval/report.py --write    # replaces the block between the markers in README.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
README = HERE.parent / "README.md"
START, END = "<!-- resultados:inicio -->", "<!-- resultados:fim -->"

CATEGORIES = {
    "add": "fato novo", "complement": "complementa sem substituir", "update": "substitui",
    "delete": "apaga", "duplicate": "repetido (ignora)",
    "nothing": "sem fato (cumprimento, comando)",
    "assistant_only": "só o assistente disse", "long": "conversa longa",
}


def latest(pattern: str) -> dict[str, dict]:
    """The newest file of each tag (model or embedder), by date in the file name."""
    chosen: dict[str, tuple[str, dict]] = {}
    for path in sorted((HERE / "results").glob(pattern)):
        data = json.loads(path.read_text(encoding="utf-8"))
        tag = path.stem.split("-", 4)[-1]
        chosen[tag] = (path.name, data)
    return {tag: {"file": name, **data} for tag, (name, data) in chosen.items()}


def pct(a: int, b: int) -> str:
    return f"{a}/{b} ({100 * a / b:.1f}%)".replace(".", ",") if b else "—"


def secs(value) -> str:
    return f"{value:.1f} s".replace(".", ",") if value is not None else "—"


def ms(value: float) -> str:
    return f"{value:.0f} ms"


def machine(result: dict) -> str:
    m = result["machine"]
    return f"{m['os']}, CPU {m['cpu']}, Python {m['python']}"


def memory_section(results: dict[str, dict]) -> list[str]:
    if not results:
        return []
    ranked = sorted(results.values(), key=lambda r: r["passed"], reverse=True)
    lines = ["### Memória: decisões de guardar, substituir, apagar ou ignorar", "",
             f"{ranked[0]['cases']} conversas fictícias (`eval/cases/memory.jsonl`). Um caso passa "
             "quando as memórias finais têm o que deviam ter e não guardam o que deviam ter "
             "esquecido. "
             "Apagamento indevido = uma memória que devia continuar e sumiu. Embedding "
             f"`{ranked[0]['engines']['embedder']}`, banco Qdrant local. Meta: ≥ 85% e "
             "0 apagamentos indevidos.", "",
             "| Modelo (Ollama) | Acerto | Apagamentos indevidos | Tempo por conversa (mediana) "
             "| p95 | Arquivo |",
             "|---|---|---|---|---|---|"]
    for r in ranked:
        t = r.get("add_seconds") or {}
        lines.append(f"| `{r['engines']['llm'].split(':', 1)[1]}` | {pct(r['passed'], r['cases'])} "
                     f"| {r['wrongful_deletions']} | {secs(t.get('p50'))} | {secs(t.get('p95'))} "
                     f"| `{r['file']}` |")
    if len({r["cases"] for r in ranked}) > 1:
        lines += ["", "Os modelos não foram medidos com o mesmo número de casos "
                  "(casos novos entram "
                  "quando um erro real é encontrado): compare pela fração de cada linha."]
    lines += ["", "Acerto por tipo de caso:", "",
              "| Tipo | " + " | ".join(f"`{r['engines']['llm'].split(':', 1)[1]}`" for r in ranked)
              + " |", "|---|" + "---|" * len(ranked)]
    for key, label in CATEGORIES.items():
        cells = []
        for r in ranked:
            c = r["by_category"].get(key)
            cells.append(f"{c['passed']}/{c['total']}" if c else "—")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    best = ranked[0]
    lines += ["", f"Casos que falharam com `{best['engines']['llm'].split(':', 1)[1]}`:", ""]
    for f in best["failures"]:
        detail = []
        if f["missing"]:
            detail.append("faltou " + ", ".join(f"“{k}”" for k in f["missing"]))
        if f["present"]:
            detail.append("sobrou " + ", ".join(f"“{k}”" for k in f["present"]))
        if f["too_many"]:
            detail.append("memórias demais")
        if f["lost"]:
            detail.append("apagou indevidamente")
        final = "; ".join(f"“{t}”" for t in f["final"]) or "nenhuma"
        lines.append(f"- `{f['case']}`: {', '.join(detail)}. Memórias finais: {final}.")
    lines += ["", f"Máquina: {machine(best)}. Data: {best['date']}."]
    return lines


def documents_section(results: dict[str, dict]) -> list[str]:
    if not results:
        return []
    r = sorted(results.values(), key=lambda x: x["date"])[-1]
    lines = ["### Documentos: busca com citação", "",
             f"{r['questions']} perguntas em linguagem natural (com palavras diferentes das do "
             "texto) "
             f"e {r['exact_terms']} termos exatos (códigos, nomes, números) sobre 7 documentos "
             "fictícios em todos os formatos (`eval/fixtures/`). Acerto = o trecho com a resposta "
             "(arquivo + página, slide, aba ou seção) está entre os 3 primeiros. Termo exato = o "
             f"1º resultado contém o termo. Embedding `{r['engines']['embedder']}`. "
             "Metas: ≥ 90% e ≥ 95%.", "",
             "| Banco | Trecho certo no top 3 | Citação certa nos acertos | Termo exato em 1º "
             "| Busca (mediana) | Busca p95 | Indexação dos 7 arquivos |",
             "|---|---|---|---|---|---|---|"]
    for name, s in r["stores"].items():
        top3, total = (int(x) for x in s["top3"].split("/"))
        first, n_exact = (int(x) for x in s["exact_first"].split("/"))
        lines.append(f"| {name} | {pct(top3, total)} | {s['citation_correct_of_hits']} "
                     f"| {pct(first, n_exact)} | {ms(s['search_p50_ms'])} "
                     f"| {ms(s['search_p95_ms'])} "
                     f"| {secs(s['index_seconds'])} |")
    lines += ["", "Casos que falharam:", ""]
    for f in r["failures"]:
        asked = f.get("question") or f.get("term")
        got = "; ".join(f["got"]) or "nada"
        lines.append(f"- {f['store']}, `{f['case']}` “{asked}”: esperado “{f['wanted']}”, "
                     f"veio {got}.")
    lines += ["", f"Arquivo: `{r['file']}`. Máquina: {machine(r)}. Data: {r['date']}."]
    return lines


def speed_section(results: dict[str, dict]) -> list[str]:
    if not results:
        return []
    r = sorted(results.values(), key=lambda x: x["date"])[-1]
    e = r["query_embedding"]
    lines = ["### Velocidade da busca", "",
             "Banco carregado com textos fictícios e vetores aleatórios de "
             f"{r['dimension']} dimensões (mede o banco e a busca híbrida; calcular 50 mil "
             "embeddings reais em CPU levaria horas). A pergunta é transformada em vetor pelo "
             f"modelo real `{r['embedder']}`: mediana {secs_ms(e['p50'])}, p95 "
             f"{secs_ms(e['p95'])}. Total = busca + vetor da pergunta. Meta: p95 < 1 s com 10 mil "
             "memórias ou 50 mil trechos.", "",
             "| Banco | Registros | Busca (mediana) | Busca p95 | **Total p95** | Carga |",
             "|---|---|---|---|---|---|"]
    for item in r["results"].values():
        s = item["search"]
        records = f"{item['records']:,}".replace(",", ".")
        lines.append(f"| {item['store']} | {records} | {secs_ms(s['p50'])} "
                     f"| {secs_ms(s['p95'])} | **{secs_ms(item['total_p95'])}** "
                     f"| {secs(item['load_seconds'] + item['bm25_index_seconds'])} |")
    lines += ["", "O banco em memória (`MemoryStore`, Python puro) só foi medido até 10 mil "
              "registros: ele serve para testes e usos pequenos.", "",
              f"Arquivo: `{r['file']}`. Máquina: {machine(r)}. Data: {r['date']}."]
    return lines


def secs_ms(value: float) -> str:
    return f"{value * 1000:.0f} ms" if value < 1 else secs(value)


def build() -> str:
    sections = [memory_section(latest("*-memory-*.json")),
                documents_section(latest("*-documents-*.json")),
                speed_section(latest("*-speed-*.json"))]
    body: list[str] = []
    for section in (s for s in sections if s):
        body += ([""] if body else []) + section
    return "\n".join([START, *body, END])


def main() -> None:
    parser = argparse.ArgumentParser(description="Tabelas de resultados para o README.")
    parser.add_argument("--write", action="store_true", help="atualiza o README.md")
    args = parser.parse_args()
    block = build()
    if not args.write:
        print(block)
        return
    text = README.read_text(encoding="utf-8")
    if START not in text or END not in text:
        raise SystemExit(f"README.md precisa dos marcadores {START} e {END}")
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    README.write_text(head + block + tail, encoding="utf-8")
    print("README.md atualizado")


if __name__ == "__main__":
    main()
