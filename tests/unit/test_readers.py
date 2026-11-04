import importlib.util

import pytest

from pi_memory.errors import UnreadableDocumentError, UnsupportedFormatError
from pi_memory.readers.registry import ReaderRegistry
from tests.docs import FILES

REG = ReaderRegistry()
needs_pdf = pytest.mark.skipif(not importlib.util.find_spec("pypdf"), reason="extra pdf")


def read(name):
    return REG.read(FILES[name], name)


@needs_pdf
def test_pdf_one_section_per_page():
    sections = read("contrato_exemplo.pdf")
    assert len(sections) == 20
    page12 = sections[11]
    assert page12.location == "página 12"
    assert "45 dias corridos" in page12.text
    assert "NF-4521" in sections[6].text


@needs_pdf
def test_scanned_pdf_has_no_text():
    assert read("escaneado.pdf") == []


@needs_pdf
def test_corrupted_pdf_is_unreadable():
    with pytest.raises(UnreadableDocumentError, match="quebrado.pdf"):
        REG.read(b"%PDF-1.4 lixo", "quebrado.pdf")


def test_docx_paragraphs_and_table():
    sections = read("relatorio.docx")
    assert [s.location for s in sections] == ["trecho 1"]
    assert "cláusula 7.2" in sections[0].text
    assert "Sul | R$ 1,2 milhão" in sections[0].text


def test_pptx_slides_and_notes():
    by_location = {s.location: s.text for s in read("apresentacao.pptx")}
    assert list(by_location) == ["slide 1", "slide 2", "slide 3", "slide 3 (notas)"]
    assert "Sul e Sudeste" in by_location["slide 2"]
    assert "120 clientes" in by_location["slide 3 (notas)"]
    assert not by_location["slide 3 (notas)"].strip().endswith("3")   # slide number dropped


def test_xlsx_sheets_with_header():
    by_location = {s.location: s.text for s in read("vendas.xlsx")}
    assert list(by_location) == ["aba Vendas, linhas 1–5", "aba Clientes, linhas 1–3"]
    assert "Nota: NF-4521 | Cliente: Padaria Imaginária | Valor: 430" in by_location[
        "aba Vendas, linhas 1–5"]


def test_markdown_sections_by_heading():
    by_location = {s.location: s.text for s in read("notas.md")}
    assert list(by_location) == ["seção Notas da reunião", "seção Pagamento", "seção Equipe"]
    assert "vence no dia 15" in by_location["seção Pagamento"]


def test_txt_with_cp1252_fallback():
    sections = read("manual.txt")
    assert sections[0].location == "trecho 1"
    assert "descalcificante" in sections[0].text and "Use apenas água" in sections[0].text


def test_csv_rows_with_header():
    sections = read("estoque.csv")
    assert sections[0].location == "linhas 2–4"
    assert "produto: Porca M8 | estoque: 950 | fornecedor: Metalúrgica Fictícia" in sections[0].text


def test_corrupted_office_file_is_unreadable():
    with pytest.raises(UnreadableDocumentError, match="planilha.xlsx"):
        REG.read(b"isto nao e zip", "planilha.xlsx")


def test_unknown_extension_lists_formats_and_custom_readers():
    with pytest.raises(UnsupportedFormatError) as info:
        REG.read(b"x", "foto.heic")
    assert ".pdf" in info.value.message and "readers=" in info.value.message


def test_user_reader_takes_precedence():
    from pi_memory.interfaces import Section

    class Mine:
        extensions = frozenset({".txt", ".xyz"})

        def read(self, data, filename):
            return [Section("tudo", data.decode())]

    registry = ReaderRegistry([Mine()])
    assert registry.read(b"oi", "a.txt")[0].location == "tudo"
    assert registry.read(b"oi", "a.xyz")[0].text == "oi"
    assert ".xyz" in registry.supported()
