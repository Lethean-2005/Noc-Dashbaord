"""Tests for the Telegram Site Down alert's threshold/caching logic —
rewritten this session to read the already-synced incident_site_down cache
instead of running its own live Postgres query every cycle. These tests
lock in that the threshold filter, outage_min computation, and mirroring
into telegram_alert_cache still work now that the data source changed.
"""

from app.services.telegram.telegram_alert import (
    _build_excel_bytes,
    _inc_wo_link,
    _incident_link,
    _site_down_over_threshold,
)


class FakeIncidentSiteDownRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self, table):
        return self._rows


class FakeTelegramCacheRepo:
    def __init__(self):
        self.written = None

    def replace_all(self, table, rows):
        self.written = rows


def _site_down_row(incident_id, occurred_at, **overrides):
    row = {
        "incident_id": incident_id,
        "incident_numeric_id": 1,
        "incident_status": "New",
        "wo_id": "WO1",
        "wo_numeric_id": 1,
        "wo_created_at": "2026-01-01 00:00:00",
        "wo_status": "New",
        "site_name": "Site A",
        "site_code": "S1",
        "occurred_at": occurred_at,
        "l1_noc_investigation_result": "",
        "last_comments": "checking",
        "nms": "Nokia",
        "hub_site": "",
        "site_grade": "",
        "province": "",
        "district": "",
        "commune": "",
    }
    row.update(overrides)
    return row


def test_only_rows_past_threshold_are_returned(app):
    with app.app_context():
        rows = [
            _site_down_row("OLD1", "2020-01-01 00:00:00"),  # way over any threshold
            _site_down_row("NEW1", "2099-01-01 00:00:00"),  # in the future -> ~0 min outage
        ]
        source_repo = FakeIncidentSiteDownRepo(rows)
        cache_repo = FakeTelegramCacheRepo()

        over_threshold = _site_down_over_threshold(240, source_repo, cache_repo)

        assert [row["incident_id"] for row in over_threshold] == ["OLD1"]


def test_every_row_is_cached_regardless_of_threshold(app):
    with app.app_context():
        rows = [
            _site_down_row("OLD1", "2020-01-01 00:00:00"),
            _site_down_row("NEW1", "2099-01-01 00:00:00"),
        ]
        source_repo = FakeIncidentSiteDownRepo(rows)
        cache_repo = FakeTelegramCacheRepo()

        _site_down_over_threshold(240, source_repo, cache_repo)

        assert len(cache_repo.written) == 2
        assert all("outage_min" in row for row in cache_repo.written)


def test_last_comments_and_nms_survive_the_switch_to_the_shared_cache(app):
    with app.app_context():
        rows = [
            _site_down_row("OLD1", "2020-01-01 00:00:00", last_comments="on-site now", nms="Huawei")
        ]
        source_repo = FakeIncidentSiteDownRepo(rows)
        cache_repo = FakeTelegramCacheRepo()

        over_threshold = _site_down_over_threshold(1, source_repo, cache_repo)

        assert over_threshold[0]["last_comments"] == "on-site now"
        assert over_threshold[0]["nms"] == "Huawei"


def test_results_sorted_longest_outage_first(app):
    with app.app_context():
        rows = [
            _site_down_row("SHORT1", "2025-01-01 00:00:00"),
            _site_down_row("LONG1", "2020-01-01 00:00:00"),
        ]
        source_repo = FakeIncidentSiteDownRepo(rows)
        cache_repo = FakeTelegramCacheRepo()

        over_threshold = _site_down_over_threshold(1, source_repo, cache_repo)

        assert [row["incident_id"] for row in over_threshold] == ["LONG1", "SHORT1"]


def test_build_excel_bytes_returns_a_valid_xlsx(app):
    with app.app_context():
        rows = [_site_down_row("OLD1", "2020-01-01 00:00:00")]
        rows[0]["outage_min"] = 300
        columns = (
            ("Incident ID", "incident_id"),
            ("Outage", lambda r: r["outage_min"]),
        )

        data = _build_excel_bytes(columns, rows, "Test Alert")

        assert data is not None
        assert data[:2] == b"PK"  # .xlsx is a zip archive


def test_build_excel_bytes_with_no_rows_still_returns_a_header_only_sheet(app):
    with app.app_context():
        columns = (("Incident ID", "incident_id"),)

        data = _build_excel_bytes(columns, [], "Test Alert")

        assert data is not None
        assert data[:2] == b"PK"


def test_incident_link_builds_the_dashboard_form_url_when_numeric_id_present():
    assert _incident_link({"incident_numeric_id": 123}) == (
        "https://prd-web-mc.cellcard.com.kh/incident/form/123"
    )


def test_incident_link_is_none_without_a_numeric_id():
    assert _incident_link({"incident_numeric_id": None}) is None
    assert _incident_link({}) is None


def test_inc_wo_link_builds_the_dashboard_form_url_when_numeric_id_present():
    assert _inc_wo_link({"wo_numeric_id": 456}) == "https://prd-web-mc.cellcard.com.kh/inc_wo/form/456"


def test_inc_wo_link_is_none_without_a_numeric_id():
    assert _inc_wo_link({"wo_numeric_id": None}) is None


def test_build_excel_bytes_hyperlinks_rows_with_a_numeric_id_only(app):
    with app.app_context():
        rows = [
            _site_down_row("HASLINK", "2020-01-01 00:00:00", incident_numeric_id=1, wo_numeric_id=2),
            _site_down_row("NOLINK", "2020-01-01 00:00:00", incident_numeric_id=None, wo_numeric_id=None),
        ]
        columns = (("Incident ID", "incident_id"), ("INC-WO ID", "wo_id"))

        data = _build_excel_bytes(
            columns, rows, "Test Alert", hyperlinks={"Incident ID": _incident_link, "INC-WO ID": _inc_wo_link}
        )

        from openpyxl import load_workbook
        import io

        ws = load_workbook(io.BytesIO(data)).active
        assert ws.cell(row=3, column=1).hyperlink.target == "https://prd-web-mc.cellcard.com.kh/incident/form/1"
        assert ws.cell(row=4, column=1).hyperlink is None


def test_telegram_excel_uses_huawei_sans_and_preserves_title_and_filters(app):
    import io
    from openpyxl import load_workbook
    with app.app_context():
        data = _build_excel_bytes([("Site Code", "site_code")], [{"site_code": "0048"}], "Site Down Alerts")
    wb = load_workbook(io.BytesIO(data))
    sheet = wb.active
    assert sheet["A1"].value.startswith("Site Down Alerts")
    assert sheet["A2"].value == "Site Code"
    assert sheet["A3"].value == "0048"
    assert sheet.auto_filter.ref == "A2:A3"
    assert sheet.freeze_panes == "A3"
    assert all(cell.font.name == "Huawei Sans" for row in sheet for cell in row if cell.value is not None)
    wb.close()
