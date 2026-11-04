"""Fictitious documents of every supported format, built with the standard library only, so tests
and the evaluation are reproducible. All names, numbers and companies are invented.

    python eval/fixtures/make_fixtures.py        # writes the files next to this script
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent

# ── PDF ──────────────────────────────────────────────────────────────────────────────────────────
CONTRACT_PAGES = {
    1: "Contrato de prestação de serviços entre a Empresa Exemplo Ltda e a Loja Fictícia SA.",
    2: "Objeto: manutenção mensal de equipamentos de refrigeração das lojas.",
    3: "As visitas técnicas acontecem na primeira segunda-feira de cada mês.",
    4: "O atendimento emergencial deve começar em até quatro horas após o chamado.",
    5: "Peças de reposição são cobradas à parte, com tabela anexa.",
    6: "O responsável técnico da contratada é o engenheiro Fulano Exemplo.",
    7: "O faturamento é mensal e cada pagamento corresponde à nota fiscal NF-4521 e seguintes.",
    8: "Os pagamentos são feitos por boleto bancário com vencimento no dia 10.",
    9: "Reajuste anual pelo índice de preços combinado entre as partes.",
    10: "A contratante fornece acesso às áreas técnicas durante o horário comercial.",
    11: "Seguro de responsabilidade civil é obrigação da contratada.",
    12: "O prazo de entrega dos relatórios técnicos é de 45 dias corridos após cada visita.",
    13: "Confidencialidade: as partes não divulgam informações comerciais da outra.",
    14: "Rescisão com aviso prévio de 30 dias, sem multa após o primeiro ano.",
    15: "A multa por atraso no pagamento é de 2% sobre o valor da parcela.",
    16: "Treinamento anual da equipe da contratante está incluído no preço.",
    17: "Equipamentos novos entram no contrato mediante aditivo assinado.",
    18: "Comunicações oficiais são feitas por e-mail corporativo das partes.",
    19: "Foro da comarca de Cidade Exemplo para dirimir dúvidas.",
    20: "Assinam o contrato os representantes legais das duas empresas.",
}


def _pdf(pages: list[list[str]], draw_only: bool = False) -> bytes:
    """A minimal valid PDF: one page per item, Helvetica, WinAnsi (accents work)."""
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
               b"/Encoding /WinAnsiEncoding >>")
    pages_id = len(objects) + 1 + 2 * len(pages)   # reserved below
    page_ids = []
    for lines in pages:
        if draw_only:
            stream = b"0.5 g 72 300 450 300 re f"
        else:
            parts = [b"BT /F1 12 Tf 72 750 Td 16 TL"]
            for line in lines:
                text = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
                parts.append(b"(" + text.encode("cp1252") + b") Tj T*")
            parts.append(b"ET")
            stream = b"\n".join(parts)
        content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        page_ids.append(add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] "
                            b"/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
                            % (pages_id, font, content)))
    kids = b" ".join(b"%d 0 R" % p for p in page_ids)
    assert add(b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(page_ids))) == pages_id
    catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % number + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
              % (len(objects) + 1, catalog, xref))
    return out.getvalue()


def contract_pdf() -> bytes:
    return _pdf([[f"Página {n}", text] for n, text in sorted(CONTRACT_PAGES.items())])


def scanned_pdf() -> bytes:
    return _pdf([[]], draw_only=True)


# ── Office (zip packages of XML) ─────────────────────────────────────────────────────────────────
_CT = ('<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/'
       'package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/>'
       '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
       'relationships+xml"/></Types>')
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PR = "http://schemas.openxmlformats.org/package/2006/relationships"


def _zip(files: dict[str, str]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        # fixed date inside the package: the same bytes on every run (reproducible fixtures)
        for name, text in {"[Content_Types].xml": _CT, **files}.items():
            z.writestr(zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)), text,
                       compress_type=zipfile.ZIP_DEFLATED)
    return out.getvalue()


def _rels(items: list[tuple[str, str, str]]) -> str:
    body = "".join(f'<Relationship Id="{i}" Type="{t}" Target="{target}"/>'
                   for i, t, target in items)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            f'<Relationships xmlns="{_PR}">{body}</Relationships>')


REPORT_PARAGRAPHS = [
    "Relatório trimestral da Empresa Exemplo Ltda.",
    "As vendas cresceram 12% no trimestre, puxadas pela linha de refrigeração.",
    "A cláusula 7.2 do contrato trata da multa por atraso de 2% ao mês.",
    "O novo centro de distribuição em Cidade Exemplo começa a operar em junho.",
    "A meta para o próximo trimestre é reduzir o prazo de entrega para 3 dias.",
]


def report_docx() -> bytes:
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    paragraphs = "".join(f"<w:p><w:r><w:t>{escape(p)}</w:t></w:r></w:p>" for p in REPORT_PARAGRAPHS)
    table = ("<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Região</w:t></w:r></w:p></w:tc>"
             "<w:tc><w:p><w:r><w:t>Receita</w:t></w:r></w:p></w:tc></w:tr>"
             "<w:tr><w:tc><w:p><w:r><w:t>Sul</w:t></w:r></w:p></w:tc>"
             "<w:tc><w:p><w:r><w:t>R$ 1,2 milhão</w:t></w:r></w:p></w:tc></w:tr></w:tbl>")
    document = (f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{w}"><w:body>'
                f"{paragraphs}{table}</w:body></w:document>")
    return _zip({
        "_rels/.rels": _rels([("rId1", f"{_R}/officeDocument", "word/document.xml")]),
        "word/document.xml": document,
    })


SLIDES = [
    (["Plano comercial 2027", "Empresa Exemplo Ltda"], ""),
    (["Mercados prioritários", "Sul e Sudeste", "Clientes de varejo alimentar"], ""),
    (["Metas do ano", "Crescer a carteira em 20%"],
     "As notas do orador citam a meta de 120 clientes novos até dezembro."),
]


def deck_pptx() -> bytes:
    a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    p = "http://schemas.openxmlformats.org/presentationml/2006/main"
    files = {"_rels/.rels": _rels([("rId1", f"{_R}/officeDocument", "ppt/presentation.xml")]),
             "ppt/presentation.xml": f'<p:presentation xmlns:p="{p}"/>'}

    def shape(lines):
        paras = "".join(f"<a:p><a:r><a:t>{escape(line)}</a:t></a:r></a:p>" for line in lines)
        return (f'<p:sld xmlns:p="{p}" xmlns:a="{a}"><p:cSld><p:spTree><p:sp><p:txBody>'
                f"{paras}</p:txBody></p:sp></p:spTree></p:cSld></p:sld>")

    for number, (lines, notes) in enumerate(SLIDES, 1):
        files[f"ppt/slides/slide{number}.xml"] = shape(lines)
        if notes:
            files[f"ppt/notesSlides/notesSlide{number}.xml"] = shape([notes, str(number)]).replace(
                "p:sld", "p:notes")
            files[f"ppt/slides/_rels/slide{number}.xml.rels"] = _rels(
                [("rId2", f"{_R}/notesSlide", f"../notesSlides/notesSlide{number}.xml")])
    return _zip(files)


SHEETS = {
    "Vendas": [["Nota", "Cliente", "Valor"],
               ["NF-4519", "Loja Fictícia SA", 1200],
               ["NF-4520", "Mercado Exemplo", 860],
               ["NF-4521", "Padaria Imaginária", 430],
               ["NF-4522", "Loja Fictícia SA", 2210]],
    "Clientes": [["Cliente", "Cidade"],
                 ["Loja Fictícia SA", "Cidade Exemplo"],
                 ["Mercado Exemplo", "Vila Exemplo"]],
}


def sales_xlsx() -> bytes:
    s = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    shared: list[str] = []
    files = {"_rels/.rels": _rels([("rId1", f"{_R}/officeDocument", "xl/workbook.xml")])}
    sheet_entries, rels = [], []
    for index, (name, rows) in enumerate(SHEETS.items(), 1):
        sheet_entries.append(f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>')
        rels.append((f"rId{index}", f"{_R}/worksheet", f"worksheets/sheet{index}.xml"))
        xml_rows = []
        for r, row in enumerate(rows, 1):
            cells = []
            for c, value in enumerate(row):
                ref = f"{chr(65 + c)}{r}"
                if isinstance(value, str):
                    if value not in shared:
                        shared.append(value)
                    cells.append(f'<c r="{ref}" t="s"><v>{shared.index(value)}</v></c>')
                else:
                    cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            xml_rows.append(f'<row r="{r}">{"".join(cells)}</row>')
        files[f"xl/worksheets/sheet{index}.xml"] = (
            f'<worksheet xmlns="{s}"><sheetData>{"".join(xml_rows)}</sheetData></worksheet>')
    files["xl/workbook.xml"] = (f'<workbook xmlns="{s}" xmlns:r="{_R}"><sheets>'
                                f'{"".join(sheet_entries)}</sheets></workbook>')
    files["xl/_rels/workbook.xml.rels"] = _rels(rels)
    files["xl/sharedStrings.xml"] = (
        f'<sst xmlns="{s}">' + "".join(f"<si><t>{escape(v)}</t></si>" for v in shared) + "</sst>")
    return _zip(files)


# ── Text ─────────────────────────────────────────────────────────────────────────────────────────
NOTES_MD = """# Notas da reunião

Reunião de planejamento da Empresa Exemplo.

## Pagamento

Os fornecedores recebem em 30 dias. A conta de luz vence no dia 15.

## Equipe

A equipe de vendas ganha duas pessoas em março. O treinamento é na sala Azul.
"""

TEXT_TXT = """Manual rápido da cafeteira Exemplo 3000.

Para limpar, desligue da tomada e retire o reservatório.

Use apenas água filtrada. O descalcificante deve ser aplicado a cada 60 dias.
"""

CSV = """produto;estoque;fornecedor
Parafuso M8;1200;Ferragens Exemplo
Arruela 10mm;800;Ferragens Exemplo
Porca M8;950;Metalúrgica Fictícia
"""


def all_fixtures() -> dict[str, bytes]:
    return {
        "contrato_exemplo.pdf": contract_pdf(),
        "escaneado.pdf": scanned_pdf(),
        "relatorio.docx": report_docx(),
        "apresentacao.pptx": deck_pptx(),
        "vendas.xlsx": sales_xlsx(),
        "notas.md": NOTES_MD.encode("utf-8"),
        "manual.txt": TEXT_TXT.encode("cp1252"),     # not UTF-8 on purpose: tests the fallback
        "estoque.csv": CSV.encode("utf-8"),
    }


def write(folder: Path = HERE) -> list[Path]:
    paths = []
    for name, data in all_fixtures().items():
        path = folder / name
        path.write_bytes(data)
        paths.append(path)
    return paths


if __name__ == "__main__":
    for written in write():
        print(written.name)
