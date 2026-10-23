"""Small bounded OOXML writer: explicit inline strings, never spreadsheet formulas."""

import csv
import io
import json
import re
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape
from rest_framework.exceptions import ValidationError

HEADERS = [
    "Identificador",
    "Título",
    "Descrição",
    "Entidade",
    "Unidade",
    "Categoria",
    "Demandante",
    "Responsáveis",
    "Referência",
    "Vencimento",
    "Prioridade",
    "Situação",
    "Atrasado",
    "Periodicidade",
    "Concluído em",
    "Versão do formulário",
    "Campos adicionais (JSON)",
]
INVALID_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")


def rows(occurrences):
    result = [HEADERS]
    size = 0
    for o in occurrences:
        result.append(
            [
                o.identifier,
                o.title,
                o.description,
                o.definition.entity.name,
                o.definition.unit.name,
                o.definition.category.name,
                o.definition.requester.username,
                ", ".join(sorted(a.user.username for a in o.assignments.all())),
                o.reference_date.isoformat(),
                o.due_date.isoformat(),
                o.get_priority_display(),
                o.get_status_display(),
                "Sim" if o.overdue else "Não",
                o.periodicity,
                o.completed_at.isoformat() if o.completed_at else "",
                str(o.form_version_id or ""),
                json.dumps(o.custom_values, ensure_ascii=False, sort_keys=True),
            ]
        )
        size += sum(len(value.encode("utf-8")) for value in result[-1])
        if size > 20 * 1024 * 1024:
            raise ValidationError("Dados excedem 20 MiB; restrinja os filtros.")
    return result


def csv_bytes(data):
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    for row in data:
        safe = [
            "'" + cell
            if cell.lstrip().startswith(("=", "+", "-", "@")) or cell.startswith(("\t", "\r", "\n"))
            else cell
            for cell in row
        ]
        writer.writerow(safe)
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def column(index):
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def xlsx_bytes(data):
    output = io.BytesIO()
    cells = []
    for number, row in enumerate(data, 1):
        content = []
        for index, value in enumerate(row, 1):
            if len(value) > 32767:
                raise ValidationError(
                    "Conteúdo excede o limite de célula XLSX (32767 caracteres). Use CSV ou restrinja o relatório."
                )
            text = escape(INVALID_XML.sub("", value))
            content.append(
                f'<c r="{column(index)}{number}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'
            )
        cells.append(f'<row r="{number}">{"".join(content)}</row>')
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    files = {
        "[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        "_rels/.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Compromissos" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": f'<worksheet xmlns="{ns}"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><sheetData>{"".join(cells)}</sheetData><autoFilter ref="A1:Q{len(data)}"/></worksheet>',
    }
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(
                name, '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + content
            )
    return output.getvalue()
