"""Tests for the Telegram INC-WO Site Down alert's threshold/caching
logic — same shape as tests/test_telegram_alert.py, but outage_min is
computed from wo_created_at (when the Work Order was opened) instead of
occurred_at (when the Incident happened), since a WO can be created well
after its parent incident.
"""

from app.services.telegram.telegram_inc_wo_alert import _inc_wo_site_down_over_threshold


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


def _inc_wo_site_down_row(wo_id, wo_created_at, **overrides):
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
    }
    row.update(overrides)
    return row


def test_only_rows_past_threshold_are_returned(app):
    with app.app_context():
        rows = [
            _inc_wo_site_down_row("OLD1", "2020-01-01 00:00:00"),  # way over any threshold
            _inc_wo_site_down_row("NEW1", "2099-01-01 00:00:00"),  # in the future -> ~0 min outage
        ]
        source_repo = FakeIncWoStatusRepo(rows)
        cache_repo = FakeTelegramCacheRepo()

        over_threshold = _inc_wo_site_down_over_threshold(240, source_repo, cache_repo)

        assert [row["wo_id"] for row in over_threshold] == ["OLD1"]


def test_every_row_is_cached_regardless_of_threshold(app):
    with app.app_context():
        rows = [
            _inc_wo_site_down_row("OLD1", "2020-01-01 00:00:00"),
            _inc_wo_site_down_row("NEW1", "2099-01-01 00:00:00"),
        ]
        source_repo = FakeIncWoStatusRepo(rows)
        cache_repo = FakeTelegramCacheRepo()

        _inc_wo_site_down_over_threshold(240, source_repo, cache_repo)

        assert len(cache_repo.written) == 2
        assert all("outage_min" in row for row in cache_repo.written)


def test_fault_description_and_nms_survive_the_cache_write(app):
    with app.app_context():
        rows = [
            _inc_wo_site_down_row(
                "OLD1", "2020-01-01 00:00:00", fault_description="power cut off", nms="Huawei"
            )
        ]
        source_repo = FakeIncWoStatusRepo(rows)
        cache_repo = FakeTelegramCacheRepo()

        over_threshold = _inc_wo_site_down_over_threshold(1, source_repo, cache_repo)

        assert over_threshold[0]["fault_description"] == "power cut off"
        assert over_threshold[0]["nms"] == "Huawei"


def test_results_sorted_longest_open_first(app):
    with app.app_context():
        rows = [
            _inc_wo_site_down_row("SHORT1", "2025-01-01 00:00:00"),
            _inc_wo_site_down_row("LONG1", "2020-01-01 00:00:00"),
        ]
        source_repo = FakeIncWoStatusRepo(rows)
        cache_repo = FakeTelegramCacheRepo()

        over_threshold = _inc_wo_site_down_over_threshold(1, source_repo, cache_repo)

        assert [row["wo_id"] for row in over_threshold] == ["LONG1", "SHORT1"]
