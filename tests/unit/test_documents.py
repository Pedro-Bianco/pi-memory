"""Document base: every format, citation, exact word, versions, refusals (fake engines)."""

import importlib.util

import pytest

from pi_memory.errors import NoTextError, NotFoundError, UnsupportedFormatError
from tests.docs import FILES
from tests.fakes import make_pm

needs_pdf = pytest.mark.skipif(not importlib.util.find_spec("pypdf"), reason="extra pdf")


@pytest.fixture
def pm():
    with make_pm() as instance:
        yield instance


@pytest.fixture
def folder(tmp_path):
    for name, data in FILES.items():
        (tmp_path / name).write_bytes(data)
    return tmp_path


@needs_pdf
def test_pdf_answer_on_page_12_with_citation(pm, folder):
    result = pm.documents.add(str(folder / "contrato_exemplo.pdf"), owner="ana")
    assert result["status"] == "added" and result["warnings"] == []
    document = result["document"]
    assert document["source"] == "contrato_exemplo.pdf" and document["format"] == "pdf"
    assert document["chunks"] == 20
    results = pm.documents.search("qual o prazo de entrega dos relatórios técnicos?",
                                  owner="ana", limit=3)["results"]
    labels = [r["citation"]["label"] for r in results]
    assert "contrato_exemplo.pdf, página 12" in labels
    assert results[0]["kind"] == "chunk" and results[0]["citation"]["doc_id"] == document["id"]


def test_exact_code_first_with_sheet_name(pm, folder):
    pm.documents.add(str(folder / "vendas.xlsx"), owner="ana")
    pm.documents.add(str(folder / "relatorio.docx"), owner="ana")
    first = pm.documents.search("NF-4521", owner="ana")["results"][0]
    assert "NF-4521" in first["text"]
    assert first["citation"]["label"] == "vendas.xlsx, aba Vendas, linhas 1–5"


def test_same_content_unchanged_new_content_replaced(pm, folder):
    path = folder / "notas.md"
    first = pm.documents.add(str(path), owner="ana")
    assert pm.documents.add(str(path), owner="ana")["status"] == "unchanged"
    path.write_text("# Notas\n\nTudo mudou: a reunião agora é na sala Verde.", encoding="utf-8")
    second = pm.documents.add(str(path), owner="ana")
    assert second["status"] == "replaced"
    assert second["document"]["id"] == first["document"]["id"]
    hits = pm.documents.search("sala Azul treinamento", owner="ana", limit=5)["results"]
    assert all("Azul" not in r["text"] for r in hits)
    assert pm.documents.list(owner="ana")["documents"][0]["chunks"] == 1


def test_remove_document(pm, folder):
    doc = pm.documents.add(str(folder / "manual.txt"), owner="ana")["document"]
    assert pm.documents.remove(doc["id"], owner="ana") == {"deleted_chunks": doc["chunks"]}
    assert pm.documents.search("descalcificante", owner="ana")["results"] == []
    assert pm.documents.list(owner="ana") == {"documents": []}
    with pytest.raises(NotFoundError):
        pm.documents.remove(doc["id"], owner="ana")


@needs_pdf
def test_scanned_pdf_is_refused_and_nothing_indexed(pm, folder):
    with pytest.raises(NoTextError, match="OCR"):
        pm.documents.add(str(folder / "escaneado.pdf"), owner="ana")
    assert pm.documents.list(owner="ana") == {"documents": []}


def test_unsupported_format(pm, tmp_path):
    path = tmp_path / "foto.heic"
    path.write_bytes(b"x")
    with pytest.raises(UnsupportedFormatError):
        pm.documents.add(str(path), owner="ana")


def test_add_bytes_equals_add(pm, folder):
    a = pm.documents.add(str(folder / "estoque.csv"), owner="ana")["document"]
    b = pm.documents.add_bytes("estoque.csv", FILES["estoque.csv"], owner="ana")
    assert b["status"] == "unchanged" and b["document"]["id"] == a["id"]


def test_owners_are_isolated_and_list_shows_each_document_once(pm, folder):
    pm.documents.add(str(folder / "apresentacao.pptx"), owner="ana",
                     metadata={"projeto": "vendas"})
    pm.documents.add(str(folder / "relatorio.docx"), owner="ana")
    pm.documents.add(str(folder / "apresentacao.pptx"), owner="bruno")
    listed = pm.documents.list(owner="ana")["documents"]
    assert sorted(d["source"] for d in listed) == ["apresentacao.pptx", "relatorio.docx"]
    assert next(d for d in listed if d["format"] == "pptx")["metadata"] == {"projeto": "vendas"}
    hits = pm.documents.search("120 clientes novos", owner="bruno")["results"]
    assert hits and all(r["citation"]["source"] == "apresentacao.pptx" for r in hits)
    assert hits[0]["citation"]["location"] == "slide 3 (notas)"
    only_docx = pm.documents.search("cláusula", owner="ana", filters={"format": "docx"})
    assert {r["citation"]["source"] for r in only_docx["results"]} == {"relatorio.docx"}
