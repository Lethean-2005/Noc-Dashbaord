"""Latest Smart reference sections, persistence, and backwards-compatible exports."""
from io import BytesIO
import json
from pathlib import Path

from docx import Document
from docx.table import _Cell
from werkzeug.datastructures import MultiDict

from app.services.incident_report.incident_report_service import IncidentReportService
from app.services.incident_report.smart_network_docx import build_docx
from app.utils.smart_report import reaction_delay, report_year_suffix, short_report_period


def test_period_ranges_and_report_year():
    assert short_report_period("September 2026") == "Sep 2026"
    assert short_report_period("Sep-Oct 2026") == "Sep-Oct 2026"
    assert short_report_period("September-October 2027") == "Sep-Oct 2027"
    assert short_report_period("invalid 2026") == ""
    assert report_year_suffix("Sep-Oct 2027") == "27"


def test_response_delay_uses_real_calendar_and_no_guessed_wrap():
    assert reaction_delay("22-Sep-2026 13:44", "22-Sep-2026 13:45") == "00hrs 01mins"
    assert reaction_delay("23-Sep-2026 23:38", "24-Sep-2026 00:03") == "00hrs 25mins"
    assert reaction_delay("2026-09-22 13:44:59", "2026-09-22 13:45:00") == "00hrs 00mins"
    assert reaction_delay("31-Feb-2026 12:00", "01-Mar-2026 12:00") == ""
    assert reaction_delay("22-Sep-2026 13:45", "22-Sep-2026 13:44") == ""


def test_new_sections_save_reload_and_keep_manual_credit(app):
    form = MultiDict([
        ("file_name","Latest report"),("smart_customer_name","Example customer"),
        ("smart_report_month","Sep-Oct 2027"), ("react_ticket_no","TEST-1"),
        ("react_circuit_id","CIRCUIT-A"),("react_smart_complain","22-Sep-2027 13:44"),
        ("react_tct_respond","22-Sep-2027 13:45"),("react_sla","Pass"),
        ("react_service_credit","0%"),("react_note","Response recorded"),
        ("credit_circuit","CIRCUIT-A"),("credit_oct","Manual agreed value"),
        ("credit_amount_oct","2700"),
    ])
    service=IncidentReportService()
    fields=service.parse_smart_form(form)
    assert json.loads(fields["smart_failure_to_react_json"])[0]["failure_to_react"] == "00hrs 01mins"
    report=service.get_report(service.create_report(fields))
    assert report["smart_failure_to_react"][0]["ticket_no"] == "TEST-1"
    assert report["smart_credit_note"][0]["months"]["oct"] == "Manual agreed value"
    assert report["smart_credit_amounts"]["oct"] == "2700"


def test_latest_export_preserves_structure_and_clears_reference_samples():
    doc=Document(BytesIO(build_docx({"smart_report_month":"Sep-Oct 2027"})))
    reference=Document(Path("Smart Network Report_Sep-Oct 2026_v1 (2).docx"))
    assert len(doc.tables)==6
    assert [(s.page_width,s.page_height) for s in doc.sections] == [(s.page_width,s.page_height) for s in reference.sections]
    text=" ".join(p.text for p in doc.paragraphs)+" "+" ".join(c.text for t in doc.tables for r in t.rows for c in r.cells)
    for sample in ("1979218","1977824","1998942","Need confirmation","2,700$"):
        assert sample not in text
    assert doc.tables[3].rows[0].cells[3].text=="Smart Complain"
    assert doc.tables[4].rows[0].cells[2].text=="Date Started"
    assert doc.tables[5].rows[1].cells[2].text=="Jan-27"
    assert doc.tables[5].rows[-1].cells[0].text=="Credit amount (USD)"


def test_latest_export_fills_both_new_tables_and_retains_legacy_outages():
    report={"smart_report_month":"Sep-Oct 2026",
            "smart_services_outage":[{"ticket_no":"OLD-RECORD","notes":"Saved before update"}],
            "smart_failure_to_react":[{"ticket_no":"NEW-RESPONSE","sla":"Manual SLA","service_credit":"Manual credit"}],
            "smart_credit_note":[{"circuit":"CIRCUIT-A","months":{"oct":"Agreed value"}}],
            "smart_credit_amounts":{"oct":"2700"}}
    doc=Document(BytesIO(build_docx(report)))
    assert doc.tables[3].rows[1].cells[0].text=="NEW-RESPONSE"
    assert doc.tables[3].rows[1].cells[6].text=="Manual SLA"
    assert doc.tables[4].rows[1].cells[0].text=="OLD-RECORD"
    assert doc.tables[5].rows[2].cells[11].text=="Agreed value"
    assert doc.tables[5].rows[-1].cells[11].text=="2700"


def test_all_twelve_months_save_reload_and_export(app):
    months = ('jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec')
    form = MultiDict([('smart_report_month', 'Jan-Dec 2027'), ('outage_circuit', 'MONTHLY-CIRCUIT')]
                     + [(f'outage_{month}', f'{index}%') for index, month in enumerate(months)])
    service = IncidentReportService()
    report = service.get_report(service.create_report(service.parse_smart_form(form)))
    expected = {month: f'{index}%' for index, month in enumerate(months)}
    assert report['smart_monthly_outage'][0]['months'] == expected
    assert report['smart_fault_services'][0]['months'] == expected
    doc = Document(BytesIO(build_docx(report)))
    for table_index in (1, 2):
        for index, month in enumerate(months):
            cells = [_Cell(cell, doc.tables[table_index]) for cell in doc.tables[table_index].rows[2]._tr.tc_lst]
            assert cells[2 + index].text == expected[month]


def test_revision_two_template_and_layout_are_preserved():
    from zipfile import ZipFile
    from lxml import etree

    reference_path = Path('Smart Network Report_Sep-Oct 2026_v1 (2).docx')
    template_path = Path('app/services/incident_report/template/smart_network_report_template.docx')
    assert template_path.read_bytes() == reference_path.read_bytes()
    reference = Document(reference_path)
    exported_bytes = build_docx({'smart_report_month': 'Jan-Dec 2027'})
    exported = Document(BytesIO(exported_bytes))
    assert [section._sectPr.xml for section in exported.sections] == [section._sectPr.xml for section in reference.sections]
    for actual, original in zip(exported.tables, reference.tables):
        assert actual._tbl.tblPr.xml == original._tbl.tblPr.xml
        assert actual._tbl.tblGrid.xml == original._tbl.tblGrid.xml
        for row_index in (0, 1, 2) if len(original.columns) > 9 else (0, 1):
            assert [cell.tcPr.xml for cell in actual.rows[row_index]._tr.tc_lst] == [cell.tcPr.xml for cell in original.rows[row_index]._tr.tc_lst]
    with ZipFile(reference_path) as source, ZipFile(BytesIO(exported_bytes)) as output:
        for name in source.namelist():
            if name.startswith(('word/media/', 'word/header', 'word/footer')) or name == 'word/styles.xml':
                if name.endswith('.xml'):
                    assert etree.tostring(etree.fromstring(output.read(name)), method='c14n') == etree.tostring(etree.fromstring(source.read(name)), method='c14n')
                else:
                    assert output.read(name) == source.read(name)


def test_merged_month_summary_keeps_distinct_months_in_cloned_rows():
    months = ('jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec')
    rows = [{'circuit': f'CIRCUIT-{i}', 'months': {m: f'{i}-{m}' for m in months}} for i in range(3)]
    document = Document(BytesIO(build_docx({'smart_fault_services': rows})))
    table = document.tables[2]
    assert len(table.rows) == 5
    for index, item in enumerate(rows, 2):
        cells = [_Cell(cell, table) for cell in table.rows[index]._tr.tc_lst]
        assert cells[1].text == item['circuit']
        assert [cell.text for cell in cells[2:]] == list(item['months'].values())


def test_outage_and_reaction_rows_keep_individual_reference_formatting():
    reference = Document(Path('Smart Network Report_Sep-Oct 2026_v1 (2).docx'))
    report = {'smart_failure_to_react': [{}] * 3, 'smart_services_outage': [{}] * 4}
    output = Document(BytesIO(build_docx(report)))
    for table_index in (3, 4):
        for actual, original in zip(output.tables[table_index].rows, reference.tables[table_index].rows):
            assert (actual._tr.trPr.xml if actual._tr.trPr is not None else None) == (original._tr.trPr.xml if original._tr.trPr is not None else None)
            assert [c.tcPr.xml for c in actual._tr.tc_lst] == [c.tcPr.xml for c in original._tr.tc_lst]


def test_long_outage_notes_can_expand_without_clipping():
    from docx.enum.table import WD_ROW_HEIGHT_RULE

    note = 'Long report details. ' * 80
    document = Document(BytesIO(build_docx({'smart_services_outage': [{'notes': note}]})))
    row = document.tables[4].rows[1]
    assert row.cells[7].text == note
    assert row.height_rule == WD_ROW_HEIGHT_RULE.AT_LEAST
