"""Fill the supplied Sep-Oct 2026 revision (2) without rebuilding its design.

Six tables cover inventory, monthly availability, its mirrored summary,
Failure to React, Services Outage Report, and Credit Note Summary.
Only placeholder text/data rows are replaced; source styles, section
orientations, logos, headers and footers remain in the actual template.
"""

import copy
from io import BytesIO
from pathlib import Path


from docx import Document
from docx.table import _Cell
from docx.enum.table import WD_ROW_HEIGHT_RULE
from app.utils.smart_report import report_year_suffix

_TEMPLATE_PATH = (
    Path(__file__).resolve().parent / "template" / "smart_network_report_template.docx"
)

_MONTH_KEYS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
_MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _delete_run(run):
    run._element.getparent().remove(run._element)


def _delete_paragraph(paragraph):
    p = paragraph._p
    p.getparent().remove(p)


def _set_paragraph_text(paragraph, text):
    """Replace text while preserving the first run formatting."""
    if paragraph.text == (text or ""):
        return
    runs = paragraph.runs
    if runs:
        runs[0].text = text or ""
        for r in list(runs[1:]):
            _delete_run(r)
    else:
        paragraph.add_run(text or "")


def _set_cell_value(cell, text):
    """Overwrites a cell's text while keeping its first run's formatting
    (font/size/color) exactly as the template had it."""
    if cell.text == (text or ""):
        return
    _set_paragraph_text(cell.paragraphs[0], text)
    for p in list(cell.paragraphs[1:]):
        _delete_paragraph(p)


def _clone_row(table, index):
    """Copy row XML to retain template borders, shading and fonts."""
    anchor_tr = table.rows[index]._tr
    new_tr = copy.deepcopy(anchor_tr)
    anchor_tr.addnext(new_tr)
    return table.rows[index + 1]


def _find_paragraph(document, text):
    for p in document.paragraphs:
        if p.text == text:
            return p
    raise ValueError(f"Smart Network Report template is missing expected paragraph {text!r}")


def _trim_to_one_row(table, anchor_index):
    """Keep one data row as the formatting anchor and remove sample rows."""
    while len(table.rows) > anchor_index + 1:
        last_tr = table.rows[-1]._tr
        last_tr.getparent().remove(last_tr)


def _fill_circuits_table(table, circuits):
    _trim_to_one_row(table, 1)
    row = table.rows[1]
    if not circuits:
        for cell in row.cells:
            _set_cell_value(cell, "")
        return
    for i, c in enumerate(circuits, start=1):
        if i > 1:
            row = _clone_row(table, len(table.rows) - 1)
        _set_cell_value(row.cells[0], str(i))
        _set_cell_value(row.cells[1], c.get("customer_description"))
        _set_cell_value(row.cells[2], c.get("service"))
        _set_cell_value(row.cells[3], c.get("bandwidth"))
        _set_cell_value(row.cells[4], c.get("circuit_id"))


def _monthly_cells(row):
    """One cell per visible field, regardless of Word's underlying grid spans."""
    return [_Cell(cell, row._parent) for cell in row._tr.tc_lst]


def _fill_monthly_table(table, rows, year_suffix):
    header = _monthly_cells(table.rows[1])
    for i, label in enumerate(_MONTH_LABELS):
        _set_cell_value(header[2 + i], f"{label}-{year_suffix}")

    _trim_to_one_row(table, 2)
    row = table.rows[2]
    if not rows:
        for cell in _monthly_cells(row):
            _set_cell_value(cell, "")
        return
    for i, item in enumerate(rows, start=1):
        if i > 1:
            row = _clone_row(table, len(table.rows) - 1)
        cells = _monthly_cells(row)
        _set_cell_value(cells[0], str(i))
        _set_cell_value(cells[1], item.get("circuit"))
        months = item.get("months") or {}
        for j, key in enumerate(_MONTH_KEYS):
            _set_cell_value(cells[2 + j], months.get(key))


def _fit_data_rows(table, count):
    """Keep each reference row's formatting; clone only additional rows."""
    wanted = max(1, count)
    while len(table.rows) > wanted + 1:
        row = table.rows[-1]._tr
        row.getparent().remove(row)
    while len(table.rows) < wanted + 1:
        _clone_row(table, len(table.rows) - 1)
    return list(table.rows)[1:]


def _fill_detail_table(table, items, keys):
    for row, item in zip(_fit_data_rows(table, len(items)), items or [{}]):
        changed = any(item.get(key) and row.cells[index].text != item[key]
                      for index, key in enumerate(keys))
        for column, key in enumerate(keys):
            _set_cell_value(row.cells[column], item.get(key) or "")
        if changed:
            # Retain the reference height as a minimum; longer user notes can grow.
            row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST


def _fill_outage_table(table, outages):
    _fill_detail_table(table, outages, (
        "ticket_no", "circuit_id", "date_started", "date_finished",
        "service", "issue_owner", "interruption", "notes",
    ))


def _fill_reaction_table(table, reactions):
    _fill_detail_table(table, reactions, (
        "ticket_no", "circuit_id", "occurred_time", "smart_complain", "tct_respond",
        "failure_to_react", "sla", "service_credit", "note",
    ))


def _fill_credit_table(table, credits, amounts, year_suffix):
    footer = copy.deepcopy(table.rows[-1]._tr)
    table.rows[-1]._tr.getparent().remove(table.rows[-1]._tr)
    _fill_monthly_table(table, credits, year_suffix)
    table._tbl.append(footer)
    row = table.rows[-1]
    _set_cell_value(row.cells[0], "Credit amount (USD)")
    for column, month in enumerate(_MONTH_KEYS, 2):
        _set_cell_value(row.cells[column], amounts.get(month) or "")


def build_docx(report):
    """report: a dict shaped like IncidentReportRepository._to_dict()'s
    output for a report_type == 'smart_network' row (smart_customer_name,
    smart_report_month, smart_active_circuits, smart_monthly_outage,
    smart_fault_services, smart_services_outage). Returns .docx bytes."""
    document = Document(str(_TEMPLATE_PATH))
    year_suffix = report_year_suffix(report.get("smart_report_month"))

    # "Document Title" is user-editable on the form (defaults to blank)
    # but previously had no effect on the export at all — the template's
    # own "MONTHLY REPORT" text was always left untouched. Falls back to
    # that same original title when left blank, so an existing report
    # saved before this field existed still exports identically.
    _set_paragraph_text(
        _find_paragraph(document, "MONTHLY REPORT"),
        (report.get("document_title") or "MONTHLY REPORT").upper(),
    )
    _set_paragraph_text(
        _find_paragraph(document, "SMART AXIATA"),
        (report.get("smart_customer_name") or "").upper(),
    )
    _set_paragraph_text(
        _find_paragraph(document, "Sep-Oct 2026"),
        report.get("smart_report_month") or "",
    )

    _fill_circuits_table(document.tables[0], report.get("smart_active_circuits") or [])
    _fill_monthly_table(document.tables[1], report.get("smart_monthly_outage") or [], year_suffix)
    _fill_monthly_table(document.tables[2], report.get("smart_fault_services") or [], year_suffix)
    _fill_reaction_table(document.tables[3], report.get("smart_failure_to_react") or [])
    _fill_outage_table(document.tables[4], report.get("smart_services_outage") or [])
    _fill_credit_table(document.tables[5], report.get("smart_credit_note") or [],
                       report.get("smart_credit_amounts") or {}, year_suffix)

    buf = BytesIO()
    document.save(buf)
    return buf.getvalue()
