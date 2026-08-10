"""Unit tests for the shared sync helpers extracted during the
domain-subfolder cleanup — app/services/postgres_sync_utils.py and
IncidentStatusCacheRepository.latest_by_site(). These are the pieces with
real logic (retry/backoff, timezone math, "keep the latest row per site"),
so they're worth locking in with tests instead of only being exercised
indirectly through the full sync services.
"""

from datetime import datetime, timezone

from app.repositories.incident.incident_status_cache_repository import IncidentStatusCacheRepository
from app.services.postgres_sync_utils import build_site_lookup, retry_fetch, to_local_seconds


def test_retry_fetch_succeeds_on_first_try():
    calls = []

    def fetch_fn():
        calls.append(1)
        return "ok"

    assert retry_fetch(fetch_fn, "test") == "ok"
    assert len(calls) == 1


def test_retry_fetch_succeeds_after_failures(monkeypatch):
    monkeypatch.setattr("app.services.postgres_sync_utils.time.sleep", lambda seconds: None)
    calls = []

    def fetch_fn():
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("conflict with recovery")
        return "ok"

    assert retry_fetch(fetch_fn, "test", max_attempts=5) == "ok"
    assert len(calls) == 3


def test_retry_fetch_returns_none_after_exhausting_attempts(monkeypatch):
    monkeypatch.setattr("app.services.postgres_sync_utils.time.sleep", lambda seconds: None)

    def fetch_fn():
        raise ConnectionError("conflict with recovery")

    assert retry_fetch(fetch_fn, "test", max_attempts=3) is None


def test_to_local_seconds_blank_input_returns_empty_string(app):
    with app.app_context():
        assert to_local_seconds(None) == ""
        assert to_local_seconds("") == ""


def test_to_local_seconds_converts_utc_to_configured_timezone(app):
    app.config["TIMEZONE"] = "Asia/Phnom_Penh"
    naive_utc = datetime(2026, 1, 1, 0, 0, 0)
    with app.app_context():
        assert to_local_seconds(naive_utc) == "2026-01-01 07:00:00"


def test_to_local_seconds_handles_already_tz_aware_input(app):
    app.config["TIMEZONE"] = "Asia/Phnom_Penh"
    aware_utc = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    with app.app_context():
        assert to_local_seconds(aware_utc) == "2026-01-01 07:00:00"


def test_build_site_lookup_keys_by_standard_code_and_skips_blank(app):
    class FakeRepo:
        def fetch_all(self, table):
            return [
                {"standard_code": "SITE1", "physical_location_name": "Site One"},
                {"standard_code": "", "physical_location_name": "No Code"},
                {"physical_location_name": "Missing Code Key"},
            ]

    with app.app_context():
        lookup = build_site_lookup(FakeRepo(), "site_cache")
    assert set(lookup) == {"SITE1"}
    assert lookup["SITE1"]["physical_location_name"] == "Site One"


def test_build_site_lookup_returns_empty_dict_on_read_failure(app):
    class FailingRepo:
        def fetch_all(self, table):
            raise RuntimeError("conflict with recovery")

    with app.app_context():
        assert build_site_lookup(FailingRepo(), "site_cache") == {}


def test_latest_by_site_keeps_first_seen_row_per_site():
    """Rows arrive occurred_at DESC (see order_by on the repository), so the
    first row seen per site_code is the newest one — a plain dict
    comprehension would instead silently keep the last-iterated (oldest)
    row, which was a real bug fixed this session."""
    rows = [
        {"site_code": "A", "incident_id": "newest-A"},
        {"site_code": "B", "incident_id": "only-B"},
        {"site_code": "A", "incident_id": "older-A"},
    ]
    result = IncidentStatusCacheRepository.latest_by_site(rows)
    assert result["A"]["incident_id"] == "newest-A"
    assert result["B"]["incident_id"] == "only-B"


def test_latest_by_site_skips_rows_with_no_site_code():
    rows = [{"site_code": "", "incident_id": "x"}, {"incident_id": "y"}]
    assert IncidentStatusCacheRepository.latest_by_site(rows) == {}
