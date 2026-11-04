"""Default graph renderer: one self-contained HTML file (inline CSS and JS, no CDN, no fonts from
the internet), so it opens from disk without a server and without network."""

from __future__ import annotations

import json
from importlib import resources

_PLACEHOLDER = "/*__GRAPH_JSON__*/null"


class HtmlGraphRenderer:
    def __init__(self, title: str = "Grafo da memória"):
        self.title = title
        self._template = resources.files("pi_memory.render").joinpath(
            "graph_template.html").read_text(encoding="utf-8")

    def render(self, graph: dict) -> str:
        # "</script>" or "<!--" inside a memory would break out of the <script> block (and allow
        # injection): every "<" becomes "<", the same character for the JSON parser.
        data = json.dumps(graph, ensure_ascii=False).replace("<", "\\u003c")
        title = self.title.replace("&", "&amp;").replace("<", "&lt;")
        return self._template.replace("__TITLE__", title).replace(_PLACEHOLDER, data)
