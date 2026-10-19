"""Renders an Incident Report dict into a .docx by filling in the ACTUAL
Telcotech reference template (template/incident_report_template.docx —
a copy of IR_SMART-IX1222_11-Sep-2026.docx) rather than rebuilding the
layout from scratch. This is a 100% structural clone by construction:
every font, color, border, cell width, and the logo itself are still the
original template's own — this module only overwrites the text inside
specific cells/paragraphs and leaves everything else untouched.

Document structure (found by walking the template's own XML — see this
module's own git history/commit for the inspection script):
  tables[0] — "Initial Incident Details" (3x4)
  tables[1] — "Detailed Incident Information" (4x4)
  tables[2] — one 1x1 "container" cell holding, in true document order:
    nested table (3x4)  — "Incident Description / Root Cause Analysis"
    nested table (1x1)  — "Root Cause Analysis – Chronology of Events" title
    paragraph            — "Details of Incident" (static sub-header)
    nested table (4x2)  — Incident Number/Date and Time/Time of Complaint/
                           Issue Reported
    paragraph            — "Actions Taken: ..." (single run)
    paragraph            — "Date and Time: <red date>" (label run + date runs)
    paragraphs (12)      — one per chronology event (bold time runs +
                           plain description runs) — variable-length in a
                           real report, so these are added/removed to
                           match instead of assuming exactly 12
    nested table (5x2)  — "Fault Analysis & Resolution"
"""

import base64
import copy
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Emu, Inches, Pt, RGBColor
from docx.table import Table
from docx.text.paragraph import Paragraph

_TEMPLATE_PATH = Path(__file__).resolve().parent / "template" / "incident_report_template.docx"

# Chronology event description color — same blue accent the web form's
# own calendar picker already uses (#4285f4, incident-report.css), per
# explicit request to color event description text blue.
_EVENT_DESCRIPTION_COLOR = RGBColor(0x42, 0x85, 0xF4)


def _delete_run(run):
    run._element.getparent().remove(run._element)


def _delete_paragraph(paragraph):
    p = paragraph._p
    p.getparent().remove(p)


def _set_paragraph_text(paragraph, text):
    """Same collapse-to-first-run approach as _set_cell_value() below,
    just operating directly on a body paragraph instead of a table
    cell's paragraphs[0] — used for the document title, which lives as
    its own top-level paragraph, not inside any table."""
    runs = paragraph.runs
    if runs:
        runs[0].text = text or ""
        for r in list(runs[1:]):
            _delete_run(r)
    else:
        paragraph.add_run(text or "")


def _set_cell_value(cell, text):
    """Overwrites a cell's text while keeping its FIRST run's formatting
    (font/bold/color) exactly as the template had it — the template's own
    value cells are often fragmented into several runs by Word's own
    spell-check (e.g. "11-Sep-2026" as 2-3 runs), all sharing the same
    plain formatting, so collapsing to one run loses nothing visually."""
    paragraph = cell.paragraphs[0]
    runs = paragraph.runs
    if runs:
        runs[0].text = text or ""
        for r in list(runs[1:]):
            _delete_run(r)
    else:
        paragraph.add_run(text or "")
    for p in list(cell.paragraphs[1:]):
        _delete_paragraph(p)


def _iter_block_items(parent_elm, parent):
    for child in parent_elm.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            yield "p", Paragraph(child, parent)
        elif tag == "tbl":
            yield "tbl", Table(child, parent)


def _fill_date_and_time_paragraph(paragraph, date_text):
    """run[0] is the "Date and Time: " label (plain) — untouched. Every
    run after it is the date value itself, fragmented + colored orange-
    red (EF5928) in the template; collapsed into run[1] here."""
    runs = paragraph.runs
    if len(runs) > 1:
        runs[1].text = date_text or ""
        for r in list(runs[2:]):
            _delete_run(r)
    elif runs:
        runs[0].text = f"Date and Time: {date_text or ''}"


_ACTIONS_TAKEN_DEFAULT = "Acknowledgment, Investigation, Resolution & Root Cause Analysis"


def _fill_actions_taken_paragraph(paragraph, summary_text):
    """The template's own "Actions Taken: ..." line reads identically on
    every sample report seen so far, but is user-editable here since it
    could plausibly differ for an incident that skipped a stage —
    defaults to that same standard phrase when left blank rather than
    forcing every report to retype it."""
    runs = paragraph.runs
    if runs:
        runs[0].text = f"Actions Taken: {summary_text or _ACTIONS_TAKEN_DEFAULT}"
        for r in list(runs[1:]):
            _delete_run(r)


def _fill_chronology_paragraph(paragraph, time_text, description_text):
    """Each event line is [bold orange-red time runs][blue description
    runs] (_EVENT_DESCRIPTION_COLOR) — same collapse-to-first-run
    approach as _set_cell_value(),
    split at the bold/non-bold boundary since a table cell's uniform
    formatting doesn't apply here. The bold portion is time-only
    ("13:00") — a day change isn't marked per-line here, it gets its own
    cloned "Date and Time: <date>" header paragraph instead (see
    build_docx()'s day-grouping below), so this line never needs to
    repeat a date that's already shown right above it. The template's
    own 2-3 spaces between time and description aren't consistently
    their own run — sometimes fused into the description's first run
    (e.g. "  The...", plain), but at least one line (13:00's own) has a
    SEPARATE whitespace-only run carrying a stray leftover color
    (FFC000) that was invisible there only because it held no visible
    text. Reusing THAT run's formatting for the new description would
    make the stray color visible, so any leading whitespace-only run is
    deleted outright rather than reused — the new description always
    gets a fresh "  " prefix on the first run that actually had real
    text in the template."""
    runs = paragraph.runs
    i = 0
    time_runs = []
    while i < len(runs) and runs[i].bold:
        time_runs.append(runs[i])
        i += 1
    if time_runs:
        time_runs[0].text = time_text or ""
        for r in time_runs[1:]:
            _delete_run(r)

    trailing_runs = runs[i:]
    content_idx = 0
    while content_idx < len(trailing_runs) - 1 and not trailing_runs[content_idx].text.strip():
        content_idx += 1
    for r in trailing_runs[:content_idx]:
        _delete_run(r)
    remaining = trailing_runs[content_idx:]
    if remaining:
        remaining[0].text = f"  {description_text or ''}"
        remaining[0].font.color.rgb = _EVENT_DESCRIPTION_COLOR
        for r in remaining[1:]:
            _delete_run(r)


def _is_chronology_line(text):
    return len(text) >= 5 and text[:2].isdigit() and ":" in text[:6]


def _insert_labeled_row_after(table, after_index, label, value):
    """Clones the row at `after_index` (same borders/shading/font as
    every other Fault Analysis row) and inserts a new label/value row
    right after it. python-docx only supports appending a row at the
    very end of a table — this manipulates the underlying <w:tr> XML
    directly instead, the same clone-then-insert technique this file
    already uses for chronology's own variable-length paragraphs
    (build_docx()'s day-grouping). Returns the new row."""
    anchor_tr = table.rows[after_index]._tr
    new_tr = copy.deepcopy(anchor_tr)
    anchor_tr.addnext(new_tr)
    new_row = table.rows[after_index + 1]
    _set_cell_value(new_row.cells[0], label)
    _set_cell_value(new_row.cells[1], value)
    return new_row


def _set_new_cell_text(cell, text):
    """Writes into a freshly created table cell's existing (empty)
    first paragraph rather than adding a NEW one — a fresh cell (from
    add_table()/_new_bordered_table()) always starts with exactly one
    empty paragraph already, so add_paragraph() here would leave that
    blank line sitting above the real text."""
    run = cell.paragraphs[0].add_run(text)
    run.font.name = "Times New Roman"
    run.font.size = Pt(8)
    return cell.paragraphs[0]


def _add_body_paragraph(container, text):
    """container.add_paragraph(text) on its own falls back to the
    default "Normal" style's font (Calibri), which visibly doesn't match
    the template's own body text (Times New Roman 8pt, confirmed by
    inspecting the template's existing paragraphs) — this is for content
    that has no existing template run to inherit formatting from (unlike
    _set_cell_value()'s cells), so the font has to be set explicitly.
    `container` is either the Document itself or a table _Cell — both
    expose the same add_paragraph() method, used here to let page 2's
    content live inside a bordering container cell (see
    _empty_container_like()) instead of directly in the document body."""
    paragraph = container.add_paragraph()
    run = paragraph.add_run(text)
    run.font.name = "Times New Roman"
    run.font.size = Pt(8)
    return paragraph


def _set_paragraph_top_border(paragraph):
    """Adds a plain horizontal rule directly above this paragraph — used
    for "Picture Reference", which the reference shows separated from
    Improvement Plan above it by a border line, even though (unlike
    Fault Analysis/Improvement Plan) it's plain bold text, not an orange
    header bar, so it needs its own border rather than one that comes
    from a table/cell shading."""
    pPr = paragraph._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    top = OxmlElement("w:top")
    top.set(qn("w:val"), "single")
    top.set(qn("w:sz"), "6")
    top.set(qn("w:space"), "1")
    top.set(qn("w:color"), "auto")
    pBdr.append(top)
    pPr.append(pBdr)


def _set_ordinal_label(cell, number, suffix, rest):
    """Writes "<number><superscript suffix> <rest>" into a Fault
    Analysis label cell — e.g. (2, "nd", "Cause of Outage:") produces
    "2" + a REAL superscript "nd" (w:vertAlign, not a unicode
    superscript character) + " Cause of Outage:", matching the
    reference document's own Word-autoformat-as-you-type ordinal
    styling. Reads bold/font/size off the cell's own existing first run
    rather than hardcoding them, so it keeps matching even if the
    template's label styling ever changes."""
    paragraph = cell.paragraphs[0]
    runs = paragraph.runs
    base_run = runs[0] if runs else paragraph.add_run()
    for r in list(runs[1:]):
        _delete_run(r)
    font_name, font_size, font_bold = base_run.font.name, base_run.font.size, base_run.font.bold
    base_run.text = str(number)
    base_run.font.superscript = False

    sup_run = paragraph.add_run(suffix)
    sup_run.font.superscript = True
    sup_run.font.name = font_name
    sup_run.font.size = font_size
    sup_run.font.bold = font_bold

    rest_run = paragraph.add_run(f" {rest}")
    rest_run.font.name = font_name
    rest_run.font.size = font_size
    rest_run.font.bold = font_bold

    for p in list(cell.paragraphs[1:]):
        _delete_paragraph(p)


def _prefix_fault_labels(fault_tbl, number, suffix):
    """Applies _set_ordinal_label() to all 5 data rows (skipping row 0,
    the table's own orange header) of a Fault Analysis table — used for
    both the 1st table (once a 2nd fault exists) and the 2nd table,
    reading each row's OWN current label text as `rest` so this can run
    on either an unprefixed clone or the original page-1 table without
    ever double-prefixing."""
    for row_index in (1, 2, 3, 4, 5):
        cell = fault_tbl.rows[row_index].cells[0]
        _set_ordinal_label(cell, number, suffix, cell.text)


# Matches the Fault Analysis table's own total width (confirmed by
# inspecting the template: 1692275 + 4881880 EMU) — every new bordered
# table page 2 adds (Improvement Plan, Picture Reference) uses this same
# width so all of page 2's boxes line up with each other and with the
# Fault Analysis table above them.
_CONTENT_WIDTH = Emu(1692275 + 4881880)


def _set_tight_cell_margins(table, top=40, bottom=40, left=108, right=108):
    """A table python-docx creates fresh (add_table()) gets Word's own
    default cell margins, which read visibly TALLER/roomier than the
    template's own Fault Analysis rows (confirmed by inspecting the
    template: those rows use small explicit trHeight values, ~254-411
    twips, well under what default margins alone would produce) — this
    tightens the new table's own margins to match that same compact
    look instead of looking bigger/puffier next to it."""
    tblPr = table._tbl.tblPr
    tblCellMar = OxmlElement("w:tblCellMar")
    for tag, val in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        node = OxmlElement(f"w:{tag}")
        node.set(qn("w:w"), str(val))
        node.set(qn("w:type"), "dxa")
        tblCellMar.append(node)
    tblPr.append(tblCellMar)


def _new_bordered_table(container, document, rows, cols=1):
    """A single/multi-column "Table Grid"-styled table, sized to
    _CONTENT_WIDTH — used for anything on page 2 that needs a real
    visible border (Improvement Plan's own rows, and each Picture
    Reference photo's frame) rather than free-floating text/images,
    matching how every bordered element elsewhere in this document is
    actually just a table, never a paragraph/shape border. Cell margins
    are tightened and content vertically centered to match the Fault
    Analysis table's own compact, centered row style."""
    table = container.add_table(rows=rows, cols=cols)
    table.style = document.styles["Table Grid"]
    table.autofit = False
    table.width = _CONTENT_WIDTH
    _set_tight_cell_margins(table)
    col_width = Emu(int(_CONTENT_WIDTH / cols))
    for column in table.columns:
        column.width = col_width
        for cell in column.cells:
            cell.width = col_width
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    return table


def _append_to_body(document, element):
    """Inserts `element` as the last real content in the document body,
    right before the trailing <w:sectPr> (section properties) every
    .docx must end with. document.add_paragraph()/add_table() do this
    same thing for a freshly created element; this does it for an
    element that was copy.deepcopy()'d from elsewhere in the template
    instead (a whole table, in build_docx()'s page-2 section below), so
    it keeps that source's own styling exactly rather than rebuilding
    it from scratch."""
    document.element.body.find(qn("w:sectPr")).addprevious(element)


def _append_to_cell(cell, element):
    """Same idea as _append_to_body(), but appends straight into a table
    cell's own content instead of the document body — used to build
    page 2's content INSIDE its own bordering container cell (see
    _empty_container_like())."""
    cell._tc.append(element)


def _empty_container_like(container_template, document):
    """Clones table[2]'s own OUTER <w:tbl> shell (a 1x1, "TableGrid"-
    styled, full-width floating table) but with its single cell's
    existing content stripped out. Page 1's big bordering box around
    "Incident Description" through "Fault Analysis & Resolution" isn't
    its own separate visual element — it's just this SAME container
    table, with everything else nested inside its one cell (see this
    module's own docstring). Page 2 needs that identical box around ITS
    own content, so this reuses the exact same shell (same width/style/
    floating position) rather than approximating it with a fresh plain
    table that could drift out of sync with page 1's own box."""
    new_tbl_el = copy.deepcopy(container_template._tbl)
    new_table = Table(new_tbl_el, document)
    cell = new_table.rows[0].cells[0]
    tc = cell._tc
    for child in list(tc.iterchildren()):
        tag = child.tag.split("}")[-1]
        if tag in ("p", "tbl"):
            tc.remove(child)
    return new_table, cell


def _build_second_fault_section(document, report, fault_tbl, chronology_title_tbl, container_template):
    """Page 2 — only when the incident turned out to have two distinct,
    separately confirmed root causes (see Incident_Report_PCCW-MX1052-
    MX1054.pdf, the reference this mirrors: first attributed to a
    submarine cable partner's maintenance, later found to also involve
    a separate fiber cut). `fault_tbl` is passed in already containing
    the Issued Time row build_docx() always inserts (and BEFORE it gets
    "1st " prefixed — build_docx() does that afterwards, see its own
    call site — so cloning it here picks up the plain, unprefixed
    labels), so the 2nd table ends up with the exact same 6 rows as the
    1st, just relabeled/refilled for the 2nd cause. Everything this
    builds lives inside one shared bordering container cell (cloned from
    `container_template`) rather than floating freely in the body,
    matching the reference's own single big box around all of page 2."""
    document.add_page_break()

    container_table, cell = _empty_container_like(container_template, document)
    _append_to_body(document, container_table._tbl)

    fault_tbl_2 = Table(copy.deepcopy(fault_tbl._tbl), document)
    _append_to_cell(cell, fault_tbl_2._tbl)
    # Same header text as page 1's own table ("Fault Analysis &
    # Resolution", no "(2nd Cause)" suffix) — the reference tells the
    # two tables apart purely via each row's own ordinal prefix.
    _prefix_fault_labels(fault_tbl_2, 2, "nd")
    _set_cell_value(fault_tbl_2.rows[1].cells[1], report.get("cause_of_outage_2"))
    _set_cell_value(fault_tbl_2.rows[2].cells[1], report.get("fault_gps_location_2"))
    _set_cell_value(fault_tbl_2.rows[3].cells[1], report.get("issued_time_2"))
    _set_cell_value(fault_tbl_2.rows[4].cells[1], report.get("resolution_2"))
    _set_cell_value(fault_tbl_2.rows[5].cells[1], report.get("permanent_fixed_2"))

    # A blank paragraph between adjacent tables in the same cell — two
    # <w:tbl> siblings with nothing between them render fused together
    # with no gap at all, but the reference clearly shows Fault Analysis
    # and Improvement Plan as two separate boxes with visible space
    # between them.
    cell.add_paragraph()

    # Improvement and preventive plan gets an orange section header
    # matching the rest of the document — cloning the existing 1x1
    # "Root Cause Analysis – Chronology of Events" title table for this,
    # since that's the only standalone (non-table-row) orange header
    # already in the template; every other orange band here is a table
    # row's own cell shading instead. Picture Reference, below, does NOT
    # get this treatment — the reference renders it as plain bold text.
    plan_header = Table(copy.deepcopy(chronology_title_tbl._tbl), document)
    _append_to_cell(cell, plan_header._tbl)
    _set_cell_value(plan_header.rows[0].cells[0], "Improvement and preventive plan")

    # The plan's own body is a real bordered table too (one row per
    # line), not free-floating text — matches every other section on
    # this page, where a visible border always comes from a table, never
    # a paragraph/shape border. Plain "1.Text" numbering, not a real Word
    # numbered-list style — this template has no "List Number" style
    # defined (a fresh add_paragraph(..., style=...) raises KeyError for
    # one that isn't), and the reference itself uses plain manual
    # numbering too.
    plan_items = report.get("improvement_plan") or []
    plan_table = _new_bordered_table(cell, document, rows=1 + len(plan_items))
    _set_new_cell_text(plan_table.rows[0].cells[0], "TELCOTECH will take the following actions:")
    for i, item in enumerate(plan_items, start=1):
        _set_new_cell_text(plan_table.rows[i].cells[0], f"{i}.{item}")

    # Same gap as above, between Improvement Plan's own table and
    # Picture Reference below it.
    cell.add_paragraph()

    _add_picture_reference_section(cell, report, with_top_border=True)

    # A <w:tc> conventionally ends with a trailing paragraph (every
    # Word-authored cell has one) — added last, after all real content,
    # same convention the template's own cells already follow.
    cell.add_paragraph()


def _add_picture_reference_section(cell, report, with_top_border):
    """"Picture Reference" heading (plain bold text — unlike every other
    section on this page, never an orange header bar) plus its photos,
    inline and unframed, flowing left-to-right in normal document order
    (leaving the rest of the line blank rather than being spread/
    centered across the full content width) — no table/border/frame of
    any kind around or between the photos themselves; the only border
    anywhere on page 2 is the outer container's own, at the SECTION
    level, never per-image. Shared between the second-fault page 2
    (where this follows Improvement Plan, and needs its own top border
    to visually separate from that — with_top_border=True) and the
    picture-only page 2 a single-fault report gets when it has photos
    but no second fault (see _build_picture_only_section() below), where
    it's the ONLY thing in the box and the box's own top edge is
    separation enough on its own."""
    picture_header = _add_body_paragraph(cell, "Picture Reference")
    picture_header.runs[0].font.bold = True
    if with_top_border:
        _set_paragraph_top_border(picture_header)

    pictures = report.get("picture_references") or []
    for i in range(0, len(pictures), 2):
        pair = pictures[i:i + 2]
        row_paragraph = cell.add_paragraph()
        for pic in pair:
            try:
                image_bytes = base64.b64decode(pic["data_base64"])
            except Exception:
                continue
            run = row_paragraph.add_run()
            run.add_picture(BytesIO(image_bytes), width=Inches(2.8))
            row_paragraph.add_run("   ")


def _build_picture_only_section(document, report, container_template):
    """Page 2 for a report with photos but NO second fault — just
    "Picture Reference" inside the same big bordering container every
    page-2 variant uses (see _empty_container_like()), with no 2nd Fault
    Analysis table or Improvement Plan since neither applies here (see
    IR_SMART-IX1222_15-Sep-2026.pdf, a real report shaped exactly this
    way: a single fault whose only page-2 content is its photos)."""
    document.add_page_break()
    container_table, cell = _empty_container_like(container_template, document)
    _append_to_body(document, container_table._tbl)
    _add_picture_reference_section(cell, report, with_top_border=False)
    cell.add_paragraph()


def build_docx(report):
    """report: the dict shape IncidentReportRepository._to_dict() /
    IncidentReportService.parse_form() produce — returns .docx bytes."""
    document = Document(str(_TEMPLATE_PATH))

    # Document title (paragraph 0, "Wholesale Products & Service
    # Delivery" in the template) is now editable on the form — same
    # collapse-to-first-run approach as _set_cell_value(). The static
    # "Incident Report" subtitle (paragraph 1) is dropped from the
    # export entirely rather than left blank, per the same request that
    # made the title editable.
    title_paragraph = document.paragraphs[0]
    subtitle_paragraph = document.paragraphs[1]
    _set_paragraph_text(title_paragraph, report.get("document_title") or "Official Incident Report")
    _delete_paragraph(subtitle_paragraph)

    t0 = document.tables[0]
    _set_cell_value(t0.rows[1].cells[1], report.get("incident_raised_by"))
    _set_cell_value(t0.rows[1].cells[3], report.get("incident_received_by"))
    _set_cell_value(t0.rows[2].cells[1], report.get("reported_date"))
    _set_cell_value(t0.rows[2].cells[3], report.get("service_disruption"))

    t1 = document.tables[1]
    _set_cell_value(t1.rows[1].cells[1], report.get("incident_date"))
    _set_cell_value(t1.rows[1].cells[3], report.get("report_time"))
    _set_cell_value(t1.rows[2].cells[1], report.get("incident_number"))
    _set_cell_value(t1.rows[2].cells[3], report.get("incident_category"))
    _set_cell_value(t1.rows[3].cells[1], report.get("customers_impacted"))
    _set_cell_value(t1.rows[3].cells[3], report.get("duration_of_interruption"))

    container_template = document.tables[2]
    outer_cell = container_template.rows[0].cells[0]
    nested = outer_cell.tables
    desc_tbl, chronology_title_tbl, details_tbl, fault_tbl = nested[0], nested[1], nested[2], nested[3]

    # 4 columns (Incident Number/Report Time/Restored Time/Duration) —
    # matches the original Telcotech reference exactly; Time Issue and
    # Response Time (WHSS) were dropped from this table (Report Time
    # shows raise_time's value, the same column the template's own
    # header used to label "Raise Time" before this table was reduced
    # from 6 columns back down to the reference's original 4).
    desc_row = desc_tbl.rows[2]
    _set_cell_value(desc_row.cells[0], report.get("incident_number"))
    _set_cell_value(desc_row.cells[1], report.get("raise_time"))
    _set_cell_value(desc_row.cells[2], report.get("restored_time"))
    _set_cell_value(desc_row.cells[3], report.get("duration_of_interruption"))

    _set_cell_value(details_tbl.rows[0].cells[1], report.get("incident_number"))
    _set_cell_value(details_tbl.rows[1].cells[1], report.get("details_date_and_time"))
    _set_cell_value(details_tbl.rows[2].cells[1], report.get("time_of_complaint"))
    _set_cell_value(details_tbl.rows[3].cells[1], report.get("issue_reported"))

    _set_cell_value(fault_tbl.rows[1].cells[1], report.get("cause_of_outage"))
    _set_cell_value(fault_tbl.rows[2].cells[1], report.get("fault_gps_location"))

    has_second_fault = (report.get("has_second_fault") or "").strip()

    # Issued Time wasn't part of the original 4-row Fault Analysis
    # table — only meaningful once there are two distinct causes (see
    # Incident_Report_PCCW-MX1052-MX1054.pdf), so it's inserted here
    # ONLY for a second-fault report, matching document.html's own
    # irIssuedTimeRow staying hidden otherwise; cloned from the GPS
    # Location row above (same single-line value style) rather than
    # Cause of Outage/Resolution's own multi-line textareas. Row indices
    # below shift by 1 once this insertion happens.
    resolution_row, permanent_row = 3, 4
    if has_second_fault:
        _insert_labeled_row_after(fault_tbl, 2, "Issued Time (UTC+7):", report.get("issued_time"))
        resolution_row, permanent_row = 4, 5
    _set_cell_value(fault_tbl.rows[resolution_row].cells[1], report.get("resolution"))
    _set_cell_value(fault_tbl.rows[permanent_row].cells[1], report.get("permanent_fixed"))

    items = list(_iter_block_items(outer_cell._tc, outer_cell))
    chronology_paragraphs = []
    actions_paragraph = None
    date_time_paragraph = None
    for kind, item in items:
        if kind != "p":
            continue
        text = item.text
        if text.startswith("Actions Taken:"):
            actions_paragraph = item
        elif text.startswith("Date and Time:"):
            date_time_paragraph = item
        elif _is_chronology_line(text):
            chronology_paragraphs.append(item)

    if actions_paragraph is not None:
        _fill_actions_taken_paragraph(actions_paragraph, report.get("actions_taken_summary"))

    events = report.get("chronology_events") or []
    if date_time_paragraph is not None:
        # Starts as "Incident date" above, same as before — but this is
        # now the FIRST of possibly several "Date and Time:" lines: any
        # event whose own date differs from the running day gets one
        # more of these headers cloned in right before it (see below),
        # so a chronology that rolls past midnight shows exactly where
        # the day changed instead of repeating a date on every line.
        _fill_date_and_time_paragraph(date_time_paragraph, report.get("incident_date"))
        # Margin below the header, separating it from the first event
        # line right under it — the template's own paragraph has no
        # space_after at all, so "Date and Time: <date>" and the first
        # "HH:MM  description" line otherwise sit touching with no
        # visual gap between them.
        date_time_paragraph.paragraph_format.space_after = Pt(6)

        if chronology_paragraphs:
            # Build the day-grouped render plan first, then rebuild the
            # whole block fresh from it — a header can land in the
            # MIDDLE of the list (wherever a day changes), which a fixed
            # 1:1 template-slot mapping (the old approach) can't express,
            # so every original chronology paragraph is deleted and
            # replaced by clones of these two prototypes instead.
            header_prototype = copy.deepcopy(date_time_paragraph._p)
            event_prototype = copy.deepcopy(chronology_paragraphs[0]._p)
            parent = date_time_paragraph._parent

            plan = []
            current_day = report.get("incident_date")
            for ev in events:
                ev_date = (ev.get("date") or "").strip()
                if ev_date and ev_date != current_day:
                    plan.append(("header", ev_date))
                    current_day = ev_date
                plan.append(("event", ev.get("time"), ev.get("description")))

            for p in chronology_paragraphs:
                _delete_paragraph(p)

            anchor = date_time_paragraph._p
            for item in plan:
                prototype = header_prototype if item[0] == "header" else event_prototype
                new_p_elm = copy.deepcopy(prototype)
                anchor.addnext(new_p_elm)
                anchor = new_p_elm
                new_paragraph = Paragraph(new_p_elm, parent)
                if item[0] == "header":
                    _fill_date_and_time_paragraph(new_paragraph, item[1])
                    # The template's own "Date and Time:" paragraph has
                    # space_before=0 (fine for the FIRST one, right under
                    # "Issue Reported:" above it), but a day-change header
                    # cloned in HERE sits right after the previous day's
                    # last event line with no visual gap at all otherwise
                    # — this gives every day-change header (not the
                    # first, original one) clear separation from the
                    # group above it.
                    new_paragraph.paragraph_format.space_before = Pt(12)
                else:
                    _fill_chronology_paragraph(new_paragraph, item[1], item[2])

    if has_second_fault:
        # Clone fault_tbl for the 2nd table BEFORE prefixing page 1's
        # own labels below — otherwise the clone would inherit an
        # already-"1st "-prefixed label and _prefix_fault_labels() would
        # double it up.
        _build_second_fault_section(document, report, fault_tbl, chronology_title_tbl, container_template)
        # Matches the reference's own numbering once a report has two
        # distinct causes — real superscript ordinal, see
        # _set_ordinal_label()'s own docstring for why.
        _prefix_fault_labels(fault_tbl, 1, "st")
    elif report.get("picture_references"):
        # A single fault can still have photos attached — its own
        # simpler page 2 (just Picture Reference, no 2nd Fault Analysis
        # or Improvement Plan) rather than no page 2 at all.
        _build_picture_only_section(document, report, container_template)

    buf = BytesIO()
    document.save(buf)
    return buf.getvalue()
