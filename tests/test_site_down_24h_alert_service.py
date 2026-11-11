"""Regression test for a real, confirmed-live bug: the Site Down 24h
Teams restore-confirmation message showed its "Restored" and (in a real
edge case) "Incident/Outage Start" timestamps 7 hours early — raw UTC
straight off Postgres, not converted to Phnom Penh local time like the
original down-alert correctly does.

Root cause: check_and_send_restore_alerts() reads "active" incidents'
occurred_at from the local SQLite cache (already converted to local time
by the sync pipeline's own to_local_seconds()), but fetches resolved
incidents' Occurred At/Restored At straight from Postgres via
IncidentRepository().fetch_site_down_restored_by_ids() — a live query
that never goes through that same conversion. _parse_ts() only does a
naive strptime with no timezone math of its own, so those two raw-UTC
fields were posted to Teams as if they were already local.
"""

import base64
from datetime import datetime

from app.services.incident import site_down_24h_alert_service as svc

try:
    from openpyxl import load_workbook

    _HAS_OPENPYXL_FOR_TESTS = True
except ImportError:
    _HAS_OPENPYXL_FOR_TESTS = False

import io

import pytest


class FakeLedger:
    def __init__(self, pending):
        self._pending = pending
        self.marked = []

    def pending_restore(self):
        return self._pending

    def mark_restore_alerted(self, incident_id):
        self.marked.append(incident_id)


class FakeActiveCacheRepo:
    """Empty — forces the restore flow through the raw-Postgres fallback
    for "Occurred At" too, the exact edge case confirmed live (an
    incident that already cleared its alarm and dropped out of
    incident_site_down before Stage 2 ran)."""

    def fetch_all(self, table):
        return []


class FakeIncidentRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_site_down_restored_by_ids(self, incident_ids):
        return self._rows


def test_restore_alert_converts_raw_postgres_utc_timestamps_to_local_time(
    app, monkeypatch
):
    # Naive UTC datetimes — exactly what Postgres hands back with no
    # session timezone set (see to_local_seconds()'s own docstring).
    # 06:54 UTC is the real raw value behind the screenshot that
    # surfaced this bug (shown there, wrongly, as "06:54" instead of the
    # correct 13:54 Phnom Penh time the original down-alert had posted
    # for the very same incident).
    raw_occurred = datetime(2026, 10, 31, 6, 54, 0)
    raw_restored = datetime(2026, 11, 2, 3, 59, 0)

    rows = [
        {
            "Incident ID": "INC1",
            "Occurred At": raw_occurred,
            "Restored At": raw_restored,
            "L1 NOC Investigation Result": "suspected power",
            "Last Comments": "",
        }
    ]

    monkeypatch.setattr(svc, "SiteDown24hAlertCacheRepository", lambda: FakeLedger([("INC1", "ref-1")]))
    monkeypatch.setattr(svc, "IncidentSiteDownCacheRepository", lambda: FakeActiveCacheRepo())
    monkeypatch.setattr(svc, "IncidentRepository", lambda: FakeIncidentRepo(rows))

    sent_html = {}

    def fake_send(html, incident_ref, *, restore=False):
        sent_html["html"] = html
        sent_html["incident_ref"] = incident_ref
        sent_html["restore"] = restore
        return True, "HTTP 200"

    monkeypatch.setattr(svc, "_send", fake_send)

    with app.app_context():
        sent = svc.check_and_send_restore_alerts()

    assert sent == 1
    # +7h (Asia/Phnom_Penh) from the raw UTC values — matching the
    # original down-alert's own already-correct "13:54", not the
    # raw-UTC "06:54" a real sent message showed before this fix.
    assert "Incident/Outage Start: 31-Oct-2026 13:54" in sent_html["html"]
    assert "Restored: 02-Nov-2026 10:59" in sent_html["html"]
    # Same ref the down-alert posted (from the ledger, not re-derived
    # live) — the restore message now names which incident it confirms
    # instead of relying solely on Teams thread context.
    assert "Incident/Work Order Ref: ref-1" in sent_html["html"]
    assert sent_html["incident_ref"] == "ref-1"
    assert sent_html["restore"] is True


def test_vip_impacted_is_a_plain_count_not_site_names():
    sites = [
        {"site_code": "3209", "site_name": "TITAN_KING_CASINO2"},
        {"site_code": "1234", "site_name": "OTHER_SITE"},
    ]
    vip_lookup = {"3209": "VIP", "1234": "VVIP"}
    assert svc._format_vip_impacted(sites, vip_lookup) == "2"


def test_vip_impacted_counts_only_vip_sites_not_every_site():
    sites = [
        {"site_code": "3209", "site_name": "TITAN_KING_CASINO2"},
        {"site_code": "9999", "site_name": "NOT_VIP_SITE"},
    ]
    vip_lookup = {"3209": "VIP"}
    assert svc._format_vip_impacted(sites, vip_lookup) == "1"


def test_vip_impacted_zero_when_no_site_is_vip():
    sites = [{"site_code": "9999", "site_name": "NOT_VIP_SITE"}]
    assert svc._format_vip_impacted(sites, {}) == "0"


def test_root_cause_text_prefers_actual_root_cause_over_l1():
    assert svc._root_cause_text("EDC grid outage", "Suspect Power") == "EDC grid outage"


def test_root_cause_text_falls_back_to_l1_when_actual_blank():
    assert svc._root_cause_text("", "Suspect Power") == "Suspect Power"


def test_root_cause_text_falls_back_to_pending_investigation_when_both_blank():
    assert svc._root_cause_text("", "") == "Pending investigation"
    assert svc._root_cause_text(None, None) == "Pending investigation"


def test_action_recovery_text_prefers_resolution_over_last_comments():
    assert svc._action_recovery_text("EDC Return", "checking with EDC") == "EDC Return"


def test_action_recovery_text_falls_back_to_last_comments_when_resolution_blank():
    assert svc._action_recovery_text("", "checking with EDC") == "checking with EDC"


def test_action_recovery_text_falls_back_to_pending_investigation_when_both_blank():
    assert svc._action_recovery_text("", "") == "Pending investigation"
    assert svc._action_recovery_text(None, None) == "Pending investigation"


def test_down_alert_ref_is_always_incident_id_even_when_a_wo_exists():
    # Previously this field preferred a real wo_id over the incident_id —
    # now it's always the Incident's own id regardless of wo_id.
    sites = [
        {
            "incident_id": "INC1",
            "incident_numeric_id": 111,
            "wo_id": "WO42",
            "wo_numeric_id": 42,
            "site_name": "Site A",
            "site_code": "S1",
            "occurred_at": "2026-11-01 20:46:00",
        }
    ]
    html = svc._build_down_alert_html(sites, services="", areas="")
    assert "Incident/Work Order Ref: " in html
    assert ">INC1<" in html
    assert "WO42" not in html


def test_down_alert_root_cause_prefers_actual_root_cause():
    sites = [
        {
            "incident_id": "INC1",
            "incident_numeric_id": 111,
            "site_name": "Site A",
            "site_code": "S1",
            "occurred_at": "2026-11-01 20:46:00",
            "l1_noc_investigation_result": "Suspect Power",
            "actual_root_cause": "power cut off",
        }
    ]
    html = svc._build_down_alert_html(sites, services="", areas="")
    assert "Root Cause: power cut off" in html
    assert "Suspect Power" not in html


def test_restore_alert_root_cause_and_action_recovery_use_actual_values(app, monkeypatch):
    raw_occurred = datetime(2026, 11, 1, 13, 46, 0)
    raw_restored = datetime(2026, 11, 2, 3, 59, 0)
    rows = [
        {
            "Incident ID": "INC1",
            "Occurred At": raw_occurred,
            "Restored At": raw_restored,
            "L1 NOC Investigation Result": "Suspect Power",
            "Actual Root Cause": "EDC grid outage - Battery backup run out",
            "Last Comments": "checking with EDC",
            "Resolution": "EDC Return",
        }
    ]

    monkeypatch.setattr(svc, "SiteDown24hAlertCacheRepository", lambda: FakeLedger([("INC1", "INC1")]))
    monkeypatch.setattr(svc, "IncidentSiteDownCacheRepository", lambda: FakeActiveCacheRepo())
    monkeypatch.setattr(svc, "IncidentRepository", lambda: FakeIncidentRepo(rows))

    sent_html = {}

    def fake_send(html, incident_ref, *, restore=False):
        sent_html["html"] = html
        return True, "HTTP 200"

    monkeypatch.setattr(svc, "_send", fake_send)

    with app.app_context():
        svc.check_and_send_restore_alerts()

    assert "Root Cause: EDC grid outage - Battery backup run out" in sent_html["html"]
    assert "Action Recovery: EDC Return" in sent_html["html"]
    assert "Suspect Power" not in sent_html["html"]
    assert "checking with EDC" not in sent_html["html"]


def _excel_site_row(**overrides):
    row = {
        "site_name": "TITAN_KING_CASINO2",
        "site_code": "3209",
        "province": "Svay Rieng",
        "district": "Bavet",
        "commune": "Bavet",
        "site_grade": "Diamond",
    }
    row.update(overrides)
    return row


@pytest.mark.skipif(not _HAS_OPENPYXL_FOR_TESTS, reason="openpyxl not installed")
def test_build_multi_site_excel_has_expected_headers_and_row_values(app):
    sites = [
        _excel_site_row(site_code="3209", site_name="TITAN_KING_CASINO2"),
        _excel_site_row(site_code="1210", site_name="TRUNG_PHUM_VILLAGE", province="Takeo"),
    ]
    tech_lookup = {"3209": ["2g", "4g"], "1210": ["2g"]}
    vip_lookup = {"3209": "VIP"}
    ran_name_lookup = {"3209": "NSiPST3209", "1210": "NSiPST1210"}
    onair_lookup = {"3209": {"lat": 11.1, "long": 105.1}, "1210": {"lat": 10.9, "long": 104.6}}

    with app.app_context():
        excel_bytes = svc._build_multi_site_excel(
            sites, tech_lookup, vip_lookup, ran_name_lookup, onair_lookup
        )
    assert excel_bytes is not None

    wb = load_workbook(io.BytesIO(excel_bytes))
    ws = wb.active
    headers = [c.value for c in ws[1]]
    assert headers == [h for h, _ in svc._EXCEL_COLUMNS]

    row1 = {headers[i]: c.value for i, c in enumerate(ws[2])}
    assert row1["№"] == 1
    assert row1["SITE_NAME"] == "TITAN_KING_CASINO2"
    assert row1["SITE_CODE"] == "3209"
    assert row1["RAN_NAME"] == "NSiPST3209"
    assert row1["TECH_SERVICES"] == "2G/4G"
    assert row1["AFFECTED_SERVICES"] == "2G/4G"
    assert row1["VIP"] == "VIP"
    assert row1["Longitude"] == 105.1
    assert row1["Latitude"] == 11.1

    row2 = {headers[i]: c.value for i, c in enumerate(ws[3])}
    assert row2["№"] == 2
    assert row2["VIP"] == "—"  # not VIP -> blank, rendered as the sheet's own "—" placeholder


def test_send_includes_base64_excel_when_given(app, monkeypatch):
    captured = {}

    def fake_post_json(url, payload):
        captured["payload"] = payload

        class Resp:
            status = 200

        return Resp()

    monkeypatch.setattr(svc, "_post_json", fake_post_json)
    with app.app_context():
        app.config["SITE_DOWN_24H_ALERT_WEBHOOK_URL"] = "https://example.invalid/webhook"
        ok, reason = svc._send(
            "<b>hi</b>", "INC1", excel_bytes=b"fake-xlsx-bytes", excel_filename="INC1-sites.xlsx"
        )

    assert ok is True
    assert captured["payload"]["excel_filename"] == "INC1-sites.xlsx"
    assert base64.b64decode(captured["payload"]["excel_base64"]) == b"fake-xlsx-bytes"


def test_send_omits_excel_fields_when_not_given(app, monkeypatch):
    captured = {}

    def fake_post_json(url, payload):
        captured["payload"] = payload

        class Resp:
            status = 200

        return Resp()

    monkeypatch.setattr(svc, "_post_json", fake_post_json)
    with app.app_context():
        app.config["SITE_DOWN_24H_ALERT_WEBHOOK_URL"] = "https://example.invalid/webhook"
        svc._send("<b>hi</b>", "INC1")

    assert "excel_base64" not in captured["payload"]
    assert "excel_filename" not in captured["payload"]


def test_grouping_counts_each_site_once_per_incident():
    rows = [
        {"incident_id": "INC1", "site_code": "0460"},
        {"incident_id": "INC1", "site_code": "0460"},
        {"incident_id": "INC1", "site_code": "1002"},
        {"incident_id": "INC2", "site_code": "0460"},
    ]
    groups = svc._group_by_incident(rows)
    assert [(ref, len(sites)) for ref, sites in groups] == [("INC1", 2), ("INC2", 1)]


def test_earliest_occurred_ignores_invalid_dates():
    assert svc._earliest_occurred([
        {"occurred_at": "invalid"}, {"occurred_at": "2026-11-05 02:34:00"},
        {"occurred_at": None},
    ]) == datetime(2026, 11, 5, 2, 34)


def test_down_alert_escapes_notes_and_site_names():
    html = svc._build_down_alert_html([{
        "incident_id": "INC1", "site_code": "0460", "site_name": "A & B",
        "last_comments": "<script>bad</script>",
    }], services="2G/4G", areas="")
    assert "A &amp; B" in html
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


@pytest.mark.parametrize("excel_result, expected_sent", [(b"workbook", 1), (None, 0)])
def test_multi_site_send_attaches_workbook_before_marking_sent(app, monkeypatch, excel_result, expected_sent):
    class Ledger:
        marked = []
        def already_down_alerted(self, ref):
            return False
        def mark_down_alerted(self, *args):
            self.marked.append(args)
    ledger = Ledger()
    rows = [dict(_excel_site_row(site_code=code), incident_id="INC1",
                 occurred_at="2026-11-01 02:34:00") for code in ["0460", "1002", "0460"]]
    class Cache:
        def fetch_all(self, table):
            return rows
    monkeypatch.setattr(svc, "SiteDown24hAlertCacheRepository", lambda: ledger)
    monkeypatch.setattr(svc, "IncidentSiteDownCacheRepository", Cache)
    for name in ["_build_tech_lookup", "_build_vip_lookup", "_build_ran_name_lookup", "_build_onair_lookup"]:
        monkeypatch.setattr(svc, name, lambda: {})
    monkeypatch.setattr(svc, "_now_local", lambda: datetime(2026, 11, 5, 10))
    monkeypatch.setattr(svc, "_build_multi_site_excel", lambda *args: excel_result)
    sent = []
    def send(html, ref, **kwargs):
        sent.append((html, ref, kwargs))
        return True, "HTTP 200"
    monkeypatch.setattr(svc, "_send", send)
    with app.app_context():
        assert svc.check_and_send_down_alerts() == expected_sent
    assert len(ledger.marked) == expected_sent
    assert len(sent) == expected_sent
    if expected_sent:
        assert "Number of Sites Impacted: 2" in sent[0][0]
        assert sent[0][2]["excel_bytes"] == b"workbook"
        assert sent[0][2]["excel_filename"] == "Incident Report 2 Sites Down - INC1.xlsx"


@pytest.mark.parametrize("value", ["0", "", None])
def test_down_alert_always_shows_zero_vip_impact(value):
    html = svc._build_down_alert_html(
        [{"incident_id": "INC1", "site_code": "9999"}],
        services="", areas="", vip_impacted=value,
    )
    assert "<li>VIP/VVIP Impacted: 0</li>" in html


def test_multi_site_message_has_short_title_counts_and_province_summary():
    sites = [dict(incident_id="INC1", site_code=str(i), site_name=f"SITE_{i}",
                  province="Phnom Penh" if i < 5 else "Kampong Cham",
                  district="DISTRICT", commune="COMMUNE",
                  hub_site="hub-mw" if i < 3 else "Not Hub") for i in range(10)]
    areas = svc._format_areas_impacted(sites)
    assert areas == "Phnom Penh / Kampong Cham"
    assert svc._build_down_alert_title(sites) == "10 Sites down over 24hrs"
    html = svc._build_down_alert_html(sites, "2G/4G", areas)
    assert "Number of Sites Impacted: 10" in html
    assert "Hub Sites Impacted: 3" in html
    assert "Areas Impacted: Phnom Penh / Kampong Cham" in html
    assert "Site Name:" not in html
    assert "Site Code:" not in html
    assert "DISTRICT" not in html
    assert "COMMUNE" not in html


def test_single_site_keeps_name_code_and_full_location():
    sites = [dict(incident_id="INC1", site_name="SITE_A", site_code="0048",
                  province="Koh Kong", district="Kaoh Kong", commune="Ta Tai Kraom")]
    areas = svc._format_areas_impacted(sites)
    assert areas == "Koh Kong Pro, Kaoh Kong Dis, Ta Tai Kraom Com"
    html = svc._build_down_alert_html(sites, "2G/4G", areas)
    assert "Site Name: SITE_A" in html
    assert "Site Code: 0048" in html
    assert "Hub Sites Impacted:" not in html


def test_provinces_trim_and_deduplicate_ignoring_case():
    assert svc._format_areas_impacted([
        {"province": " Phnom Penh "}, {"province": "phnom penh"},
        {"province": None}, {"province": "Kampong Cham"},
    ]) == "Phnom Penh / Kampong Cham"


def test_hub_count_uses_unique_site_codes():
    assert svc._count_hub_sites([
        {"site_code": "0048", "hub_site": "hub-mw"},
        {"site_code": "0048", "hub_site": "hub-router"},
        {"site_code": "0125", "hub_site": "HUB-ROUTER"},
        {"site_code": "1002", "hub_site": "Not Hub"},
    ]) == 2


@pytest.mark.skipif(not _HAS_OPENPYXL_FOR_TESTS, reason="openpyxl not installed")
def test_excel_has_no_filters_and_uses_single_line_huawei_sans(app):
    sites = [_excel_site_row(site_code="0048"), _excel_site_row(site_code="0125")]
    with app.app_context():
        data = svc._build_multi_site_excel(sites, {}, {}, {}, {})
    sheet = load_workbook(io.BytesIO(data)).active
    assert sheet.auto_filter.ref is None
    assert sheet.freeze_panes == "A2"
    assert sheet["A1"].value == chr(0x2116)
    assert not sheet.merged_cells.ranges
    assert all("Incident Report - Impacted Sites" not in str(cell.value or "") for row in sheet for cell in row)
    for row in sheet:
        for cell in row:
            if cell.value is not None:
                assert cell.font.name == "Huawei Sans"
                assert not cell.font.bold
                assert not cell.alignment.wrap_text
    assert sheet["C2"].value == "0048"
    assert sheet["C2"].data_type == "s"
    assert sheet["B2"].alignment.horizontal == "left"
    assert sheet["B2"].border.left.style == "thin"


def test_restore_body_matches_example_and_escapes_source_text():
    start = datetime(2026, 11, 6, 2, 40)
    finish = datetime(2026, 11, 6, 4, 33)
    html = svc._build_restore_alert_html("INC1", start, finish, "Power cut off", "", "Temporary run mobile DG", "")
    assert html.startswith("Dear All,<br>Please be informed that the incident report above has been restored.")
    assert "Incident/Outage Start: 06-Nov-2026 02:40" in html
    assert "Restored: 06-Nov-2026 04:33" in html
    assert "Outage Duration(DD:HH:MM): 00:01:53" in html
    assert html.count("<li>") == 6
    assert "Incident/Work Order Ref: INC1" in html
    assert html.endswith("Best Regards,<br>Work Flow Sitedown-alert")
    escaped = svc._build_restore_alert_html("INC1", start, finish, "<script>test</script>", "", "<b>source</b>", "")
    assert "<script>" not in escaped and "&lt;script&gt;" in escaped
    assert "<b>source</b>" not in escaped


def test_restore_with_invalid_timestamps_is_not_sent(app, monkeypatch):
    rows = [{"Incident ID": "INC1", "Occurred At": datetime(2026, 11, 6, 5),
             "Restored At": datetime(2026, 11, 6, 3)}]
    monkeypatch.setattr(svc, "SiteDown24hAlertCacheRepository", lambda: FakeLedger([("INC1", "INC1")]))
    monkeypatch.setattr(svc, "IncidentSiteDownCacheRepository", lambda: FakeActiveCacheRepo())
    monkeypatch.setattr(svc, "IncidentRepository", lambda: FakeIncidentRepo(rows))
    calls = []
    monkeypatch.setattr(svc, "_send", lambda *args, **kwargs: calls.append(args))
    with app.app_context():
        assert svc.check_and_send_restore_alerts() == 0
    assert calls == []


def test_restore_uses_only_actual_root_cause_and_resolution():
    html = svc._build_restore_alert_html("INC1", datetime(2026, 11, 6, 2), datetime(2026, 11, 6, 4), "", "Suspected old cause", "", "Unconfirmed old comment")
    assert "Root Cause: Not recorded" in html
    assert "Action Recovery: Not recorded" in html
    assert "Suspected old cause" not in html
    assert "Unconfirmed old comment" not in html


def test_two_incidents_with_identical_sites_have_distinct_files_and_no_repeat_send(app, monkeypatch):
    import io
    from openpyxl import load_workbook
    class Ledger:
        seen = set()
        def already_down_alerted(self, ref):
            return ref in self.seen
        def mark_down_alerted(self, ref, site, correlation):
            assert correlation == ref
            self.seen.add(ref)
    ledger = Ledger()
    rows = [dict(_excel_site_row(site_code=code), incident_id=ref,
                 occurred_at="2026-11-01 02:34:00")
            for ref in ("INC1", "INC2") for code in ("0460", "1002", "0460")]
    class Cache:
        def fetch_all(self, table):
            return rows
    monkeypatch.setattr(svc, "SiteDown24hAlertCacheRepository", lambda: ledger)
    monkeypatch.setattr(svc, "IncidentSiteDownCacheRepository", Cache)
    for name in ("_build_tech_lookup", "_build_vip_lookup", "_build_ran_name_lookup", "_build_onair_lookup"):
        monkeypatch.setattr(svc, name, lambda: {})
    monkeypatch.setattr(svc, "_now_local", lambda: datetime(2026, 11, 5, 10))
    sent = []
    def fake_send(html, ref, **kwargs):
        sent.append((ref, kwargs))
        return True, "HTTP 202"
    monkeypatch.setattr(svc, "_send", fake_send)
    with app.app_context():
        assert svc.check_and_send_down_alerts() == 2
        assert svc.check_and_send_down_alerts() == 0
    assert [ref for ref, _ in sent] == ["INC1", "INC2"]
    assert {data["excel_filename"] for _, data in sent} == {
        "Incident Report 2 Sites Down - INC1.xlsx", "Incident Report 2 Sites Down - INC2.xlsx"}
    for _, data in sent:
        workbook = load_workbook(io.BytesIO(data["excel_bytes"]))
        sheet = workbook.active
        assert sheet.max_row == 3  # column headers and two unique sites; no title row
        assert [sheet.cell(row, 3).value for row in (2, 3)] == ["0460", "1002"]
        workbook.close()


@pytest.mark.skipif(not _HAS_OPENPYXL_FOR_TESTS, reason="openpyxl not installed")
def test_excel_columns_fit_long_single_line_records(app):
    name = "W" * 80
    sites = [_excel_site_row(site_code="0048", site_name=name), _excel_site_row(site_code="0125", site_name="First\nSecond")]
    with app.app_context():
        data = svc._build_multi_site_excel(sites, {}, {}, {}, {})
    sheet = load_workbook(io.BytesIO(data)).active
    assert sheet.column_dimensions["B"].width > 60
    assert sheet["B2"].value == name
    assert sheet["B3"].value == "First Second"
    assert sheet.auto_filter.ref is None
    assert not sheet["B2"].alignment.wrap_text
    assert not sheet["B1"].alignment.wrap_text
