"""Graph page: one self-contained file that opens without internet."""

import json
import re

from pi_memory import cli
from pi_memory.render.html import HtmlGraphRenderer
from tests.fakes import make_pm
from tests.unit.test_graph import seed


def embedded(html: str) -> dict:
    match = re.search(r'<script id="graph-data" type="application/json">(.*?)</script>', html,
                      re.DOTALL)
    return json.loads(match.group(1))


def test_page_embeds_the_graph_and_needs_no_network():
    with make_pm() as pm:
        seed(pm)
        graph = pm.graph.data("ana")
        html = pm.graph.html("ana")
    assert html.lstrip().startswith("<!DOCTYPE html>")
    assert embedded(html)["nodes"] == graph["nodes"]
    assert not re.search(r"""(src|href)\s*=\s*["']?(https?:)?//""", html)
    assert "@import" not in html and "fetch(" not in html


def test_script_closing_tags_in_texts_are_escaped():
    graph = {"owner": "ana", "generated_at": "2026-11-04T00:00:00Z", "edges": [],
             "nodes": [{"id": "m:1", "kind": "memory", "label": "x", "topic": "outros",
                        "text": "</script><script>alert(1)</script>"}]}
    html = HtmlGraphRenderer().render(graph)
    assert html.count("</script>") == html.count("<script")   # no early close
    assert embedded(html)["nodes"][0]["text"] == "</script><script>alert(1)</script>"


def test_empty_graph_page_says_so():
    with make_pm() as pm:
        html = pm.graph.html("ninguem")
    assert "nenhuma memória ainda" in html
    assert embedded(html)["nodes"] == []


def test_html_to_file_returns_the_path(tmp_path):
    out = tmp_path / "grafo.html"
    with make_pm() as pm:
        seed(pm)
        assert pm.graph.html("ana", path=str(out)) == str(out)
    assert embedded(out.read_text(encoding="utf-8"))["owner"] == "ana"


def test_cli_graph_html_writes_the_file(tmp_path, monkeypatch, capsys):
    pm = make_pm()
    seed(pm)
    monkeypatch.setattr(cli, "open_memory", lambda args: pm)
    out = tmp_path / "g.html"
    assert cli.main(["graph", "html", "--owner", "ana", "--out", str(out)]) == 0
    assert out.exists()
    assert json.loads(capsys.readouterr().out) == {"path": str(out)}
