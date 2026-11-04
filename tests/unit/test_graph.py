"""Memory graph: memories grouped by topic, as JSON."""

from tests.fakes import make_pm

NODE_KEYS = {"topic": {"id", "kind", "label", "topic"},
             "memory": {"id", "kind", "label", "topic", "text"}}
EDGE_KEYS = {"belongs": {"source", "target", "kind"},
             "similar": {"source", "target", "kind", "weight"}}


def seed(pm):
    ids = {}
    for text, topic in [("O usuário trabalha como enfermeira no hospital", "trabalho"),
                        ("O usuário faz plantão noturno no hospital", "trabalho"),
                        ("O usuário corre 5 km toda manhã", "saúde"),
                        ("O usuário tem uma filha chamada Lia", "família"),
                        ("O usuário tem um filho chamado Davi", "família")]:
        ids[text] = pm.memories.remember(text, owner="ana", topic=topic)["id"]
    pm.memories.remember("O usuário mora em Vila Exemplo", owner="bruno", topic="casa")
    return ids


def test_graph_nodes_and_edges():
    with make_pm() as pm:
        ids = seed(pm)
        graph = pm.graph.data("ana")
    assert graph["owner"] == "ana" and graph["generated_at"].endswith("Z")
    topics = {n["id"] for n in graph["nodes"] if n["kind"] == "topic"}
    assert topics == {"t:trabalho", "t:saúde", "t:família"}
    memories = [n for n in graph["nodes"] if n["kind"] == "memory"]
    assert {n["id"] for n in memories} == {f"m:{i}" for i in ids.values()}
    assert all(set(n) == NODE_KEYS[n["kind"]] for n in graph["nodes"])
    assert all(set(e) == EDGE_KEYS[e["kind"]] for e in graph["edges"])

    belongs = {(e["source"], e["target"]) for e in graph["edges"] if e["kind"] == "belongs"}
    assert len(belongs) == 5
    assert (f"m:{ids['O usuário corre 5 km toda manhã']}", "t:saúde") in belongs

    similar = [e for e in graph["edges"] if e["kind"] == "similar"]
    pairs = {frozenset((e["source"], e["target"])) for e in similar}
    assert len(pairs) == len(similar) == 2          # one pair per topic with 2 memories, once
    nurse = f"m:{ids['O usuário trabalha como enfermeira no hospital']}"
    night = f"m:{ids['O usuário faz plantão noturno no hospital']}"
    assert frozenset((nurse, night)) in pairs
    assert all(0 < e["weight"] <= 1 for e in similar)


def test_empty_memory_gives_an_empty_graph():
    with make_pm() as pm:
        graph = pm.graph.data("ninguem")
    assert graph["nodes"] == [] and graph["edges"] == []
