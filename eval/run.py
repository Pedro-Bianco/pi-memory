"""Evaluation with real engines (rule: measure before claiming): numbers in the README come from
the files this script writes to eval/results/.

    python eval/run.py --suite memory [--llm-model qwen2.5:14b] [--embedding-model ...] [--limit N]

memory: each case starts from its prior memories, runs memories.add and checks the final state:
  - pass: every "contains" keyword is in some memory, no "absent" keyword is in any memory, and
    the number of memories is at most "max_memories" (when given);
  - wrongful deletion: a "keep" memory that no longer exists (an update is not a deletion).
Keywords are compared without accents and case.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import date
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from pi_memory import PiMemory, __version__, config  # noqa: E402
from pi_memory._util import plain  # noqa: E402


def _versions(*packages: str) -> dict:
    found = {}
    for name in packages:
        try:
            found[name] = version(name)
        except PackageNotFoundError:
            pass
    return found


def _machine() -> dict:
    return {"os": platform.platform(), "python": platform.python_version(),
            "cpu": platform.processor() or platform.machine()}


def _percentiles(values: list[float]) -> dict:
    ordered = sorted(values)
    if not ordered:
        return {}
    return {"p50": round(ordered[len(ordered) // 2], 2),
            "p95": round(ordered[max(0, int(len(ordered) * 0.95) - 1)], 2),
            "max": round(ordered[-1], 2), "mean": round(sum(ordered) / len(ordered), 2)}


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() or c in ".-" else "-" for c in text)


def load_cases(name: str, limit: int | None) -> list[dict]:
    lines = (HERE / "cases" / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
    cases = [json.loads(line) for line in lines if line.strip()]
    return cases[:limit] if limit else cases


def run_memory(args) -> dict:
    from pi_memory.engines.embedders.fastembed import FastEmbedEmbedder
    from pi_memory.engines.llms.ollama import OllamaLLM
    from pi_memory.engines.stores.qdrant import QdrantStore

    embedder = FastEmbedEmbedder(args.embedding_model, cache_dir=args.embedding_cache)
    llm = OllamaLLM(args.llm_model, timeout=args.timeout)
    cases = load_cases("memory", args.limit)
    by_category: dict[str, Counter] = defaultdict(Counter)
    failures, wrongful = [], []
    events = Counter()
    latencies = []
    started = time.perf_counter()
    for case in cases:
        with tempfile.TemporaryDirectory() as folder, PiMemory(
                embedder=embedder, llm=llm, store=QdrantStore(path=folder),
                timeout=args.timeout) as pm:
            prior = {text: pm.memories.remember(text, owner="eval")["id"]
                     for text in case["prior"]}
            t0 = time.perf_counter()
            decisions = pm.memories.add(case["messages"], owner="eval")["decisions"]
            seconds = time.perf_counter() - t0
            latencies.append(seconds)
            final = [m["text"] for m in pm.memories.list(owner="eval", limit=1000)["memories"]]
            final_ids = {m["id"] for m in pm.memories.list(owner="eval", limit=1000)["memories"]}
        events.update(d["event"] for d in decisions)
        blob = [plain(t) for t in final]
        missing = [k for k in case["contains"] if not any(plain(k) in t for t in blob)]
        present = [k for k in case["absent"] if any(plain(k) in t for t in blob)]
        too_many = "max_memories" in case and len(final) > case["max_memories"]
        lost = [t for t in case["keep"] if prior[t] not in final_ids]
        ok = not missing and not present and not too_many
        by_category[case["category"]]["total"] += 1
        by_category[case["category"]]["passed"] += int(ok)
        if lost:
            wrongful.append({"case": case["id"], "lost": lost})
        if not ok or lost:
            failures.append({"case": case["id"], "missing": missing, "present": present,
                             "too_many": too_many, "lost": lost, "final": final,
                             "decisions": decisions, "seconds": round(seconds, 2)})
        print(f"{'ok ' if ok and not lost else 'ERR'} {case['id']:<16} {seconds:5.1f}s",
              flush=True)
    total = sum(c["total"] for c in by_category.values())
    passed = sum(c["passed"] for c in by_category.values())
    return {
        "suite": "memory",
        "cases": total,
        "passed": passed,
        "accuracy": round(passed / total, 4) if total else None,
        "wrongful_deletions": len(wrongful),
        "by_category": {k: {"passed": v["passed"], "total": v["total"]}
                        for k, v in sorted(by_category.items())},
        "events": dict(events),
        "add_seconds": _percentiles(latencies),
        "seconds_total": round(time.perf_counter() - started, 1),
        "engines": {"embedder": embedder.name, "llm": f"ollama:{args.llm_model}",
                    "store": "qdrant-local"},
        "wrongful": wrongful,
        "failures": failures,
        "tag": args.llm_model,
        "summary": {"cases": total, "passed": passed,
                    "accuracy": round(passed / total, 4) if total else None,
                    "wrongful_deletions": len(wrongful)},
    }


def _stores(tmp: str, chroma: bool = False) -> dict:
    """Every installed store gets the same questions (exact terms must work in any store)."""
    from pi_memory.engines.stores.memory import MemoryStore
    stores = {"memory": lambda: MemoryStore()}
    try:
        from pi_memory.engines.stores.qdrant import QdrantStore
        QdrantStore  # noqa: B018
        stores["qdrant-local"] = lambda: QdrantStore(path=str(Path(tmp) / "qdrant"))
    except ImportError:
        pass
    if chroma:
        try:
            from pi_memory.engines.stores.chroma import ChromaStore
            ChromaStore  # noqa: B018
            stores["chroma"] = lambda: ChromaStore(path=str(Path(tmp) / "chroma"))
        except ImportError:
            pass
    return stores


def run_documents(args) -> dict:
    """Top-3 hit rate of the right piece (source + location); exact terms: the first piece
    contains the term."""
    from pi_memory.engines.embedders.fastembed import FastEmbedEmbedder
    sys.path.insert(0, str(HERE / "fixtures"))
    from make_fixtures import all_fixtures

    embedder = FastEmbedEmbedder(args.embedding_model, cache_dir=args.embedding_cache)
    questions = load_cases("documents", args.limit)
    exact = load_cases("exact_terms", args.limit)
    per_store, failures = {}, []
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as tmp:
        for store_name, make_store in _stores(tmp).items():
            t_index = time.perf_counter()
            with PiMemory(embedder=embedder, llm=lambda prompt: "", store=make_store()) as pm:
                for name, data in all_fixtures().items():
                    if name != "escaneado.pdf":
                        pm.documents.add_bytes(name, data, owner="eval")
                index_seconds = time.perf_counter() - t_index
                top3 = cited = first = 0
                latencies = []
                for case in questions:
                    t0 = time.perf_counter()
                    results = pm.documents.search(case["question"], owner="eval", limit=3)
                    latencies.append(time.perf_counter() - t0)
                    wanted = f"{case['source']}, {case['location']}"
                    labels = [r["citation"]["label"] for r in results["results"]]
                    if wanted in labels:
                        top3 += 1
                        cited += 1   # the label is the citation: hit means citation right
                    else:
                        failures.append({"store": store_name, "case": case["id"],
                                         "question": case["question"], "wanted": wanted,
                                         "got": labels})
                for case in exact:
                    results = pm.documents.search(case["term"], owner="eval", limit=3)["results"]
                    wanted = f"{case['source']}, {case['location']}"
                    # the term may exist in more than one document (NF-4521 does): what exact
                    # search must guarantee is that the first piece contains it
                    if results and plain(case["term"]) in plain(results[0]["text"]):
                        first += 1
                    else:
                        failures.append({"store": store_name, "case": case["id"],
                                         "term": case["term"], "wanted": wanted,
                                         "got": [r["citation"]["label"] for r in results]})
            latencies.sort()
            per_store[store_name] = {
                "top3": f"{top3}/{len(questions)}",
                "top3_rate": round(top3 / len(questions), 4),
                "citation_correct_of_hits": f"{cited}/{top3}",
                "exact_first": f"{first}/{len(exact)}",
                "exact_first_rate": round(first / len(exact), 4),
                "index_seconds": round(index_seconds, 1),
                "search_p50_ms": round(1000 * latencies[len(latencies) // 2], 1),
                "search_p95_ms": round(1000 * latencies[int(len(latencies) * 0.95) - 1], 1),
            }
            print(store_name, per_store[store_name], flush=True)
    return {"suite": "documents", "stores": per_store, "questions": len(questions),
            "exact_terms": len(exact), "seconds_total": round(time.perf_counter() - started, 1),
            "engines": {"embedder": embedder.name}, "failures": failures,
            "tag": args.embedding_model.split("/")[-1],
            "summary": {s: {k: v[k] for k in ("top3", "exact_first")}
                        for s, v in per_store.items()}}


WORDS = ("contrato prazo entrega relatório visita técnica pagamento boleto multa atraso cliente "
         "loja mercado padaria nota fiscal estoque parafuso arruela reunião equipe treinamento "
         "sala projeto orçamento cidade exemplo usuário gosta trabalha mora tem filha gata café "
         "jazz corrida plantão hospital enfermeira manual cafeteira limpeza água semana "
         "mês").split()


def _fake_corpus(n: int, dimension: int, seed: int):
    """Fictitious texts and random unit vectors: measures the store and the hybrid search, not
    the embedding model (computing 50 000 real embeddings on CPU would take hours)."""
    import random

    from pi_memory._util import unit
    from pi_memory.interfaces import Record
    from pi_memory.search import terms

    rng = random.Random(seed)
    for i in range(n):
        words = rng.choices(WORDS, k=rng.randint(12, 60)) + [f"NF-{10000 + i}"]
        text = " ".join(words)
        vector = unit([rng.gauss(0, 1) for _ in range(dimension)])
        yield Record(f"r{i}", text, {"owner": "eval", "topic": rng.choice(WORDS)}, vector,
                     terms(text))


def run_speed(args) -> dict:
    """Search p50/p95 per store at 10 000 and 50 000 records, plus the query embedding time of
    the real default model; total = both."""
    import random

    from pi_memory._util import unit
    from pi_memory.engines.embedders.fastembed import FastEmbedEmbedder
    from pi_memory.search import BM25Index, hybrid

    embedder = FastEmbedEmbedder(args.embedding_model, cache_dir=args.embedding_cache)
    dimension = embedder.dimension
    questions = [c["question"] for c in load_cases("documents", None)][:30]
    embed_times = []
    for q in questions:
        t0 = time.perf_counter()
        embedder.embed_query(q)
        embed_times.append(time.perf_counter() - t0)
    sizes = [int(s) for s in args.sizes.split(",")]
    rng = random.Random(7)
    results = {}
    # Chroma keeps its files open on Windows after close: ignore errors removing the temp folder
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        for store_name, make_store in _stores(tmp, chroma=True).items():
            for n in sizes:
                if store_name == "memory" and n > 10000:
                    continue   # pure-Python store: for tests and small uses, not 50 000 vectors
                store = make_store()
                collection = f"speed_{n}"
                store.open_collection(collection, dimension, {})
                t0 = time.perf_counter()
                batch = []
                for record in _fake_corpus(n, dimension, seed=n):
                    batch.append(record)
                    if len(batch) == 500:
                        store.upsert(collection, batch)
                        batch = []
                if batch:
                    store.upsert(collection, batch)
                load_seconds = time.perf_counter() - t0
                index, index_seconds = None, 0.0
                if not store.native_hybrid:
                    t0 = time.perf_counter()
                    index = BM25Index()
                    for record in store.scan(collection, {}):
                        index.add(record)
                    index_seconds = time.perf_counter() - t0
                times = []
                for q in questions:
                    vector = unit([rng.gauss(0, 1) for _ in range(dimension)])
                    query = f"{q} NF-{10000 + rng.randrange(n)}"
                    t0 = time.perf_counter()
                    hits = hybrid(store, collection, vector, query, {"owner": "eval"}, 5, index)
                    times.append(time.perf_counter() - t0)
                    assert hits
                store.close()
                key = f"{store_name} · {n}"
                results[key] = {"store": store_name, "records": n,
                                "search": _percentiles(times),
                                "load_seconds": round(load_seconds, 1),
                                "bm25_index_seconds": round(index_seconds, 1)}
                print(key, results[key]["search"], flush=True)
    embed = _percentiles(embed_times)
    for item in results.values():
        item["total_p95"] = round(item["search"]["p95"] + embed["p95"], 3)
    return {"suite": "speed", "embedder": embedder.name, "dimension": dimension,
            "query_embedding": embed, "results": results,
            "tag": args.embedding_model.split("/")[-1],
            "summary": {k: v["total_p95"] for k, v in results.items()}}


SUITES = {"memory": run_memory, "documents": run_documents, "speed": run_speed}


def main() -> None:
    parser = argparse.ArgumentParser(description="Avaliação do pi-memory com motores reais.")
    parser.add_argument("--suite", choices=sorted(SUITES), required=True)
    parser.add_argument("--llm-model", default=config.DEFAULT_LLM_MODEL)
    parser.add_argument("--embedding-model", default=config.DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--embedding-cache", default=None,
                        help="pasta onde o FastEmbed guarda/procura o modelo")
    parser.add_argument("--decision-search", choices=("hybrid", "dense"), default=None,
                        help="experimento: como achar as candidatas da decisão")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--sizes", default="10000,50000", help="speed: tamanhos medidos")
    parser.add_argument("--limit", type=int, default=None, help="só os N primeiros casos")
    parser.add_argument("--out", default=None, help="arquivo de resultado (padrão: eval/results)")
    args = parser.parse_args()

    if args.decision_search:
        config.DECISION_SEARCH = args.decision_search
    result = SUITES[args.suite](args)
    result["decision_search"] = config.DECISION_SEARCH
    result.update({"date": date.today().isoformat(), "pi_memory": __version__,
                   "machine": _machine(),
                   "packages": _versions("fastembed", "qdrant-client", "httpx", "pypdf")})
    out = Path(args.out) if args.out else (
        HERE / "results" / f"{result['date']}-{args.suite}-{_slug(result.pop('tag'))}"
        f"{'-partial' if args.limit else ''}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False))
    print(f"resultado em {out}")


if __name__ == "__main__":
    main()
