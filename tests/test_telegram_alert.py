"""Tests for the Telegram Site Down alert's threshold/caching logic —
rewritten this session to read the already-synced incident_site_down cache
instead of running its own live Postgres query every cycle. These tests
lock in that the threshold filter, outage_min computation, and mirroring
into telegram_alert_cache still work now that the data source changed.
"""
from app.services.telegram.telegram_alert import _site_down_over_threshold


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
        "incident_id": incident_id, "incident_numeric_id": 1, "incident_status": "New",
        "wo_id": "WO1", "wo_numeric_id": 1, "wo_created_at": "2026-01-01 00:00:00",
        "wo_status": "New", "site_name": "Site A", "site_code": "S1",
        "occurred_at": occurred_at, "l1_noc_investigation_result": "",
        "last_comments": "checking", "nms": "Nokia", "hub_site": "", "site_grade": "",
        "province": "", "district": "", "commune": "",
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
        rows = [_site_down_row("OLD1", "2020-01-01 00:00:00", last_comments="on-site now", nms="Huawei")]
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
