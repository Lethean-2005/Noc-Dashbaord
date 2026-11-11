"""Create the requested 21-site mock alert. Network POSTs are mocked."""
import base64
import io
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from app import create_app
from app.services.incident import site_down_24h_alert_service as svc

NAMES = "KOH_KONG7, AEKAKPHEAP, CHHAY_LOUK, KK083, TKK002, ANGLONG_VAK, KOH153, OU_SAOM, BAK_KHLANG_OLD, KOH_KONG2, SANKOM_THMEI, KOH_KONG1, DEI_KRAHAM, KOH_KONG6, CHEUTEAL_CHRUM, TATAI_KROM, KOH_KONG4, PREAEK_KHSACH, KRANG_RONGIENG, KAOH_SRALAU, BUOR_SANGKREACH".split(", ")
CODES = "1667, 2160, 1777, 6213, 6373, 1673, 5530, 1773, 4417, 0125, 1780, 0048, 1937, 1677, 1785, 0376, 1666, 1345, 1774, 1511, 1975".split(", ")
HUBS = {"2160", "1777", "0125", "0048", "0376", "1666", "1511"}
AREAS = "Koh Kong Pro, Khemara Phoumin Dis, Smach Mean Chey Com | Pursat Pro, Veal Veaeng Dis, Thma Da Com | Pursat Pro, Veal Veaeng Dis, Ou Saom Com | Koh Kong Pro, Khemara Phoumin Dis, Stueng Veaeng Com | Koh Kong Pro, Kaoh Kong Dis, Ta Tai Kraom Com | Koh Kong Pro, Mondol Seima Dis, Pak Khlang Com | Pursat Pro, Veal Veaeng Dis, Anlong Reab Com | Pursat Pro, Veal Veaeng Dis, Pramaoy Com | Koh Kong Pro, Mondol Seima Dis, Tuol Kokir Com | Koh Kong Pro, Kiri Sakor Dis, Preaek Khsach Com | Koh Kong Pro, Kaoh Kong Dis, Kaoh Kapi Com | Battambang Pro, Bavel Dis, Kdol Ta Haen Com"


def main():
    out = Path(__file__).resolve().parents[1] / "docs" / "previews" / "INC-0000284074-mock"
    out.mkdir(parents=True, exist_ok=True)
    sites = [dict(incident_id="INC-0000284074", site_name=name, site_code=code,
                  hub_site="hub-mw" if code in HUBS else "Not Hub",
                  source="Alarms", site_grade="Silver", occurred_at="2026-11-03 16:10:00",
                  actual_root_cause="28 site down") for name, code in zip(NAMES, CODES)]
    # Only incident-level technology/priority were supplied. Per-site details
    # (including VIP status and affected technology) remain blank in the sheet.
    with tempfile.TemporaryDirectory() as folder:
        app = create_app("testing", instance_path=folder)
        with app.app_context():
            workbook_bytes = svc._build_multi_site_excel(sites, {}, {}, {}, {})
            assert workbook_bytes
            workbook = load_workbook(io.BytesIO(workbook_bytes))
            sheet = workbook.active
            sheet.title = "Impacted Sites"
            sheet.delete_rows(1)  # Reference has the header on the first row.
            sheet["A1"] = "Nº"
            border = Border(*( [Side(style="thin", color="000000")] * 4))
            for row in sheet:
                for cell in row:
                    if cell.value == "\u2014":
                        cell.value = None
                    cell.border = border
                    cell.fill = PatternFill(fill_type=None)
                    cell.font = Font(name="Arial", size=11, color="000000")
                    cell.alignment = Alignment(vertical="center")
            for cell in sheet[1]:
                cell.fill = PatternFill("solid", fgColor="FFFF00")
                cell.font = Font(name="Arial", size=10, bold=True, color="000000")
            for cell in sheet["C"][1:]:
                cell.number_format = "@"
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = "A1:M22"
            filename = "MOCK - Incident Report 21 Sites Down - INC-0000284074.xlsx"
            workbook.save(out / filename)
            html = svc._build_down_alert_html(sites, "2G/4G", AREAS, "0")
            captured = {}
            def mock_post(url, payload):
                captured.update(payload)
                return type("Response", (), {"status": 200})()
            app.config["SITE_DOWN_24H_ALERT_WEBHOOK_URL"] = "https://example.invalid/mock-only"
            with patch.object(svc, "_post_json", mock_post):
                ok, _ = svc._send(html, "INC-0000284074", excel_bytes=(out / filename).read_bytes(), excel_filename=filename)
            assert ok
            assert base64.b64decode(captured["excel_base64"]) == (out / filename).read_bytes()
            saved = load_workbook(out / filename)
            assert saved.active.max_row == 22
            assert saved.active["C11"].value == "0125"
            assert saved.active["C13"].value == "0048"
            assert "VIP/VVIP Impacted: 0" in captured["text"]
            (out / "mock-payload.json").write_text(json.dumps(captured, indent=2), encoding="utf-8")
            import html as html_tools
            page = '<!doctype html><meta charset="utf-8"><title>21-site mock alert</title><body style="font-family:Arial;max-width:900px;margin:32px"><p><strong>LOCAL MOCK PREVIEW: no message sent.</strong></p>' + html + '<p><a href="' + html_tools.escape(filename, quote=True) + '">Download impacted sites workbook</a></p><p>Unprovided per-site fields are blank. Technology and priority in the message are incident-level values supplied by the user. Root cause says 28 sites; the supplied site list contains 21.</p></body>'
            (out / "preview.html").write_text(page, encoding="utf-8")
    print(f"Mock POST passed; 21 spreadsheet rows verified. No network sends. Files: {out}")


if __name__ == "__main__":
    main()
