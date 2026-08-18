"""Tests for the Telegram INC-WO Category Power alert's threshold/caching
logic — near-exact mirror of tests/test_telegram_inc_wo_alert.py, just
against the category='power' source table instead of 'site_down'.
"""

import app.services.telegram.telegram_inc_wo_power_alert as power_alert
from app.services.telegram.telegram_inc_wo_power_alert import (
    _inc_wo_category_power_over_threshold,
    send_inc_wo_category_power_alert,
)


class FakeIncWoStatusRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self, table):
        return self._rows


class FakeTelegramCacheRepo:
    def __init__(self):
        self.written = None

    def replace_all(self, table, rows):
        self.written = rows


def _inc_wo_power_row(wo_id, wo_created_at, **overrides):
    row = {
        "incident_id": "INC1",
        "incident_status": "In Progress",
        "wo_id": wo_id,
        "wo_created_at": wo_created_at,
        "wo_status": "New",
        "site_name": "Site A",
        "site_code": "S1",
        "fault_description": "checking",
        "nms": "Nokia",
        "hub_site": "",
        "site_grade": "",
        "province": "",
        "district": "",
        "commune": "",
        "support_level": "L2 On-Site",
    }
    row.update(overrides)
    return row


def test_only_rows_past_threshold_are_returned(app):
    with app.app_context():
        rows = [
            _inc_wo_power_row("OLD1", "2020-01-01 00:00:00"),  # way over any threshold
            _inc_wo_power_row("NEW1", "2099-01-01 00:00:00"),  # in the future -> ~0 min outage
        ]
        source_repo = FakeIncWoStatusRepo(rows)
        cache_repo = FakeTelegramCacheRepo()

        over_threshold = _inc_wo_category_power_over_threshold(240, source_repo, cache_repo)

        assert [row["wo_id"] for row in over_threshold] == ["OLD1"]


def test_every_row_is_cached_regardless_of_threshold(app):
    with app.app_context():
        rows = [
            _inc_wo_power_row("OLD1", "2020-01-01 00:00:00"),
            _inc_wo_power_row("NEW1", "2099-01-01 00:00:00"),
        ]
        source_repo = FakeIncWoStatusRepo(rows)
        cache_repo = FakeTelegramCacheRepo()

        _inc_wo_category_power_over_threshold(240, source_repo, cache_repo)

        assert len(cache_repo.written) == 2
        assert all("outage_min" in row for row in cache_repo.written)


def test_fault_description_and_nms_survive_the_cache_write(app):
    with app.app_context():
        rows = [
            _inc_wo_power_row(
                "OLD1", "2020-01-01 00:00:00", fault_description="power cut off", nms="Huawei"
            )
        ]
        source_repo = FakeIncWoStatusRepo(rows)
        cache_repo = FakeTelegramCacheRepo()

        over_threshold = _inc_wo_category_power_over_threshold(1, source_repo, cache_repo)

        assert over_threshold[0]["fault_description"] == "power cut off"
        assert over_threshold[0]["nms"] == "Huawei"


def test_results_sorted_longest_open_first(app):
    with app.app_context():
        rows = [
            _inc_wo_power_row("SHORT1", "2025-01-01 00:00:00"),
            _inc_wo_power_row("LONG1", "2020-01-01 00:00:00"),
        ]
        source_repo = FakeIncWoStatusRepo(rows)
        cache_repo = FakeTelegramCacheRepo()

        over_threshold = _inc_wo_category_power_over_threshold(1, source_repo, cache_repo)

        assert [row["wo_id"] for row in over_threshold] == ["LONG1", "SHORT1"]


def test_rows_with_no_wo_id_are_excluded_from_what_gets_sent(app):
    """A brand-new WO the source system hasn't assigned an ID to yet has
    no wo_created_at either, so it'd otherwise pass any threshold with an
    outage_min of 0 and send as a row of dashes."""
    with app.app_context():
        rows = [
            _inc_wo_power_row(None, "", site_name="", site_code=""),
            _inc_wo_power_row("REAL1", "2020-01-01 00:00:00"),
        ]
        source_repo = FakeIncWoStatusRepo(rows)
        cache_repo = FakeTelegramCacheRepo()

        over_threshold = _inc_wo_category_power_over_threshold(0, source_repo, cache_repo)

        assert [row["wo_id"] for row in over_threshold] == ["REAL1"]


def test_rows_with_no_wo_id_are_still_cached(app):
    """The raw cache mirror stays unfiltered — it's an audit trail of what
    was fetched, not of what was actually sent."""
    with app.app_context():
        rows = [
            _inc_wo_power_row(None, "", site_name="", site_code=""),
            _inc_wo_power_row("REAL1", "2020-01-01 00:00:00"),
        ]
        source_repo = FakeIncWoStatusRepo(rows)
        cache_repo = FakeTelegramCacheRepo()

        _inc_wo_category_power_over_threshold(0, source_repo, cache_repo)

        assert len(cache_repo.written) == 2


def test_only_l2_support_level_rows_are_sent(app):
    with app.app_context():
        rows = [
            _inc_wo_power_row("L3WO", "2020-01-01 00:00:00", support_level="L3 Internal Support"),
            _inc_wo_power_row("BLANKWO", "2020-01-01 00:00:00", support_level=""),
            _inc_wo_power_row("L2WO", "2020-01-01 00:00:00", support_level="L2 On-Site"),
        ]
        source_repo = FakeIncWoStatusRepo(rows)
        cache_repo = FakeTelegramCacheRepo()

        over_threshold = _inc_wo_category_power_over_threshold(0, source_repo, cache_repo)

        assert [row["wo_id"] for row in over_threshold] == ["L2WO"]


def test_non_l2_support_level_rows_are_still_cached(app):
    """Same audit-trail reasoning as the no-wo_id exclusion above."""
    with app.app_context():
        rows = [
            _inc_wo_power_row("L3WO", "2020-01-01 00:00:00", support_level="L3 Internal Support"),
            _inc_wo_power_row("L2WO", "2020-01-01 00:00:00", support_level="L2 On-Site"),
        ]
        source_repo = FakeIncWoStatusRepo(rows)
        cache_repo = FakeTelegramCacheRepo()

        _inc_wo_category_power_over_threshold(0, source_repo, cache_repo)

        assert len(cache_repo.written) == 2


def test_send_splits_into_one_image_per_25_rows(app, monkeypatch):
    """31 rows over threshold should send as 2 images (25 + 6), each
    titled "Part X/Y", not one giant image."""
    with app.app_context():
        app.config["TELEGRAM_BOT_INC_WO_POWER_TOKEN"] = "fake-token"
        app.config["TELEGRAM_CHAT_IDS_INC_WO_POWER"] = "111"

        rows = [_inc_wo_power_row(f"WO{i}", "2020-01-01 00:00:00") for i in range(31)]
        source_repo = FakeIncWoStatusRepo(rows)
        cache_repo = FakeTelegramCacheRepo()

        rendered_titles = []
        sent_count = []
        heads_up_texts = []
        monkeypatch.setattr(
            power_alert,
            "_render_inc_wo_table_image",
            lambda chunk, title: (rendered_titles.append(title), sent_count.append(len(chunk)), b"png")[-1],
        )
        monkeypatch.setattr(power_alert, "_send_telegram_document", lambda *a, **k: True)
        monkeypatch.setattr(
            power_alert,
            "_send_telegram_text",
            lambda token, chat_ids, text: (heads_up_texts.append(text), True)[-1],
        )
        monkeypatch.setattr(power_alert, "_send_telegram_excel", lambda *a, **k: True)

        result = send_inc_wo_category_power_alert(0, source_repo, cache_repo)

        assert heads_up_texts == ["INC-WO-POWER Alert — 2 Part(s)"]
        assert rendered_titles == [
            "INC-WO Category Power Alerts (Part 1/2)",
            "INC-WO Category Power Alerts (Part 2/2)",
        ]
        assert sent_count == [25, 6]
        assert result == {"sent": True, "count": 31}


def test_send_uses_plain_title_when_only_one_image_needed(app, monkeypatch):
    with app.app_context():
        app.config["TELEGRAM_BOT_INC_WO_POWER_TOKEN"] = "fake-token"
        app.config["TELEGRAM_CHAT_IDS_INC_WO_POWER"] = "111"

        rows = [_inc_wo_power_row("WO1", "2020-01-01 00:00:00")]
        source_repo = FakeIncWoStatusRepo(rows)
        cache_repo = FakeTelegramCacheRepo()

        rendered_titles = []
        monkeypatch.setattr(
            power_alert,
            "_render_inc_wo_table_image",
            lambda chunk, title: (rendered_titles.append(title), b"png")[-1],
        )
        monkeypatch.setattr(power_alert, "_send_telegram_document", lambda *a, **k: True)
        monkeypatch.setattr(power_alert, "_send_telegram_excel", lambda *a, **k: True)

        send_inc_wo_category_power_alert(0, source_repo, cache_repo)

        assert rendered_titles == ["INC-WO Category Power Alerts"]


def test_send_also_sends_excel_attachment(app, monkeypatch):
    """The Excel attachment carries every over-threshold row in one file,
    unlike the images (which chunk at 25 rows/image)."""
    with app.app_context():
        app.config["TELEGRAM_BOT_INC_WO_POWER_TOKEN"] = "fake-token"
        app.config["TELEGRAM_CHAT_IDS_INC_WO_POWER"] = "111"

        rows = [_inc_wo_power_row("WO1", "2020-01-01 00:00:00")]
        source_repo = FakeIncWoStatusRepo(rows)
        cache_repo = FakeTelegramCacheRepo()

        monkeypatch.setattr(power_alert, "_render_inc_wo_table_image", lambda chunk, title: b"png")
        monkeypatch.setattr(power_alert, "_send_telegram_document", lambda *a, **k: True)

        excel_calls = []
        monkeypatch.setattr(
            power_alert,
            "_send_telegram_excel",
            lambda token, chat_ids, excel_bytes, filename: (excel_calls.append(filename), True)[-1],
        )

        send_inc_wo_category_power_alert(0, source_repo, cache_repo)

        assert excel_calls == ["Inc-wo-power.xlsx"]
