"""Weekly history retains raw events independently of the Top 20 presentation."""
import csv
import io
from datetime import datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from lxml import html

from app.database.sql_loader import load_queries
from app.repositories.alarm.alarm_cache_repository import AlarmCacheRepository
from app.services.alarm.alarm_service import AlarmService
from app.services.alarm.alarm_sync_service import AlarmSyncService
from tests.test_congestion_blacklist import alarm

WEEK = "2026-11-16"


def event_url(download=False, **extra):
    args = dict(scope="Congestion History", congestion_week=WEEK, congestion_view="events")
    args.update(extra)
    return ("/drilldown/download?" if download else "/drilldown?") + urlencode(args)


def seed_events(count=1051):
    rows = [alarm(str(i), device_name=f"DEVICE-{i % 25:02d}",
                  down_time=f"2026-11-{16 + i % 2:02d} 12:00:00",
                  restored_time="2026-11-18 10:00:00" if i % 2 else "")
            for i in range(count)]
    rows.extend([
        alarm("previous-week", down_time="2026-11-15 23:59:59"),
        alarm("next-week", down_time="2026-11-23 00:00:00"),
    ])
    AlarmCacheRepository().replace_all("congestion_history_cache", rows)
    return rows


def test_all_week_events_are_visible_and_exported_without_top_limit(app, client):
    seed_events()
    response = client.get(event_url(row_limit="10"))
    assert response.status_code == 200
    tree = html.fromstring(response.data)
    assert len(tree.xpath('//table/tbody/tr')) == 1051
    assert "DEVICE-24" in tree.text_content()  # Beyond the chart's first 20 devices.
    assert "2026-11-18 10:00:00" in tree.text_content()
    assert "RestoreTime" in tree.text_content()
    assert "All matching alarm events for this week" not in tree.text_content()
    assert tree.xpath('//input[@aria-label="Search congestion records"]')
    export = client.get(event_url(download=True, row_limit="10"))
    records = list(csv.DictReader(io.StringIO(export.get_data(as_text=True))))
    assert len(records) == 1051
    assert len({r["Alarm ID"] for r in records}) == 1051
    assert {r["RestoreTime"] for r in records} == {"", "2026-11-18 10:00:00"}
    assert all(r["Alarm ID"] not in {"previous-week", "next-week"} for r in records)


def test_weekly_event_date_filter_and_export_keep_same_scope(app, client):
    seed_events()
    params = {"from": "2026-11-17", "to": "2026-11-17"}
    response = client.get(event_url(**params))
    tree = html.fromstring(response.data)
    assert len(tree.xpath('//table/tbody/tr')) == 525
    assert tree.xpath('//input[@name="congestion_week"]/@value') == [WEEK]
    assert tree.xpath('//input[@name="congestion_view"]/@value') == ["events"]
    link = tree.xpath('//a[contains(@href,"/drilldown/download")]/@href')[0]
    records = list(csv.DictReader(io.StringIO(client.get(link).get_data(as_text=True))))
    assert len(records) == 525
    assert all(r["DownTime"].startswith("2026-11-17") for r in records)


def test_summary_still_counts_every_alarm_without_repeating_event_rows(app, client):
    seed_events()
    service = AlarmService()
    summary = service.get_congestion_week_interface_summary(WEEK)
    assert len(summary) == 25
    assert sum(r["total_count"] for r in summary) == 1051
    response = client.get("/drilldown?" + urlencode(dict(scope="Congestion History", congestion_week=WEEK)))
    assert b"Latest DownTime" in response.data
    assert b"All alarm events" in response.data
    assert len(html.fromstring(response.data).xpath('//table/tbody/tr')) == 25
    page = client.get("/congestion")
    links = html.fromstring(page.data).xpath('//a[contains(@class,"congestion-week-link")]/@href')
    assert len(links) == 4 and all("congestion_view=events" in link for link in links)


def test_week_boundary_includes_sunday_last_second_not_next_monday(app):
    rows = [alarm("first", down_time="2026-11-16 00:00:00"),
            alarm("last", down_time="2026-11-22 23:59:59"),
            alarm("outside", down_time="2026-11-23 00:00:00")]
    AlarmCacheRepository().replace_all("congestion_history_cache", rows)
    assert {r["id"] for r in AlarmService().get_congestion_week_details(WEEK)} == {"first", "last"}


def test_sync_keeps_every_source_event_including_restored_and_non_top_devices(app, monkeypatch):
    from app.services.alarm import alarm_sync_service as module
    monkeypatch.setattr(module, "_now_local", lambda: datetime(2026, 11, 18, 12, tzinfo=ZoneInfo("Asia/Phnom_Penh")))
    class Source:
        def fetch_congestion_history(self, since):
            assert since == "2026-10-26"
            return [dict(ID=str(i), AlarmName="TCT_CONGESTION", alarm_type="congestion",
                         DeviceName=f"DEVICE-{i % 25:02d}", IPAddress="10.0.0.1", INTERFACE="GE1",
                         DownTime="2026-11-17 12:00:00", RestoredTime="2026-11-17 13:00:00" if i % 2 else None)
                    for i in range(1051)]
    assert AlarmSyncService(mssql_repository=Source()).sync_congestion_history(history_weeks=4) == 1051
    stored = AlarmCacheRepository().fetch_all("congestion_history_cache")
    assert len(stored) == 1051
    assert len({r["device_name"] for r in stored}) == 25
    assert any(r["restored_time"] for r in stored)
    assert any(not r["restored_time"] for r in stored)


def test_failed_source_fetch_preserves_existing_history(app):
    seed_events(2)
    class Unavailable:
        def fetch_congestion_history(self, since):
            raise RuntimeError("Source unavailable")
    assert AlarmSyncService(mssql_repository=Unavailable()).sync_congestion_history() is None
    assert len(AlarmCacheRepository().fetch_all("congestion_history_cache")) == 4


def test_history_source_query_has_no_active_or_top_only_restriction():
    sql = " ".join(line for line in load_queries("alarms")["congestion_history"].splitlines()
                   if not line.strip().startswith("--")).lower()
    where = sql.split("where", 1)[1]
    assert "restoredtime" not in where and "status" not in where
    assert "top " not in sql and "limit " not in sql
    assert "select distinct p.id" in sql
    assert "left join" in sql and "p.downtime >= %s" in where


def test_weekly_events_browser_search_summary_and_complete_export(app):
    import threading
    from pathlib import Path
    import pytest
    from werkzeug.serving import make_server
    playwright = pytest.importorskip("playwright.sync_api")
    if not Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe").exists():
        pytest.skip("Microsoft Edge is unavailable")
    seed_events()
    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}" + event_url(), wait_until="networkidle")
            visible_rows = page.locator(".alarm-table > tbody > tr:not(.empty-row):visible")
            playwright.expect(visible_rows).to_have_count(1051)
            search = page.get_by_label("Search congestion records", exact=True)
            search.fill("DEVICE-24")
            playwright.expect(visible_rows).to_have_count(42)
            playwright.expect(page.locator(".alarm-row-count")).to_have_text("42 records")
            search.fill("no-such-congestion-event")
            playwright.expect(visible_rows).to_have_count(0)
            playwright.expect(page.locator(".search-empty-row")).to_be_visible()
            search.fill("")
            playwright.expect(visible_rows).to_have_count(1051)
            page.get_by_role("link", name="Interface summary", exact=True).click()
            page.wait_for_load_state("networkidle")
            playwright.expect(visible_rows).to_have_count(25)
            page.get_by_role("link", name="All alarm events", exact=True).click()
            page.wait_for_load_state("networkidle")
            playwright.expect(visible_rows).to_have_count(1051)
            with page.expect_download() as pending:
                page.locator('a[href*="/drilldown/download"]').click()
            records = list(csv.DictReader(io.StringIO(Path(pending.value.path()).read_text(encoding="utf-8"))))
            assert len(records) == len({row["Alarm ID"] for row in records}) == 1051
            assert not errors
            browser.close()
    finally:
        server.shutdown()
        thread.join()


def test_history_index_upgrade_preserves_events_and_avoids_scan_or_sort(app):
    from app.database.cache import get_cache_conn, init_cache_db
    seed_events()
    conn = get_cache_conn()
    try:
        conn.execute("DROP INDEX IF EXISTS idx_congestion_history_cache_down_time")
        conn.execute("DROP INDEX IF EXISTS idx_congestion_history_cache_device_down_time")
        before = {tuple(row) for row in conn.execute("SELECT * FROM congestion_history_cache")}
        conn.commit()
    finally:
        conn.close()
    init_cache_db()
    conn = get_cache_conn()
    try:
        after = {tuple(row) for row in conn.execute("SELECT * FROM congestion_history_cache")}
        assert before == after
        for sql, args, index in [
            ("SELECT * FROM congestion_history_cache WHERE down_time >= ? AND down_time < ? ORDER BY down_time DESC", (WEEK, "2026-11-23"), "idx_congestion_history_cache_down_time"),
            ("SELECT * FROM congestion_history_cache WHERE device_name = ? ORDER BY down_time DESC", ("DEVICE-24",), "idx_congestion_history_cache_device_down_time"),
        ]:
            plan = " ".join(row[3] for row in conn.execute("EXPLAIN QUERY PLAN " + sql, args))
            assert index in plan and "TEMP B-TREE" not in plan and "SCAN congestion_history_cache" not in plan
    finally:
        conn.close()
