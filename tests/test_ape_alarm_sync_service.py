"""Tests for ApeAlarmSyncService — Site Code used to be computed by
Postgres's get_processed_site() inside ape_alarm.sql; the query now selects
raw `site`/`additional_info` and this service resolves Site Code locally via
app/utils/get_processed_site.py (see tests/test_get_processed_site.py for that logic's own
tests) using the site_lookup cache for the sran_id/nodeb_id/bts_id lookups.
"""
from app.services.ape_alarm.ape_alarm_sync_service import ApeAlarmSyncService


class FakeApeAlarmRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_active(self):
        return self._rows


class FakeSiteCacheRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self, table):
        return self._rows


class FakeSiteLookupCacheRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self, table):
        return self._rows


class FakeCacheRepo:
    def __init__(self):
        self.written = None

    def replace_all(self, table, rows):
        self.written = rows


def _source_row(**overrides):
    row = {
        "Raw Site": "SITEAB1234XY",
        "Additional Info": "",
        "Occurred At": None,
        "Event Name": "Main Failure",
        "NMS Code": "3",
        "Technology": "Power",
        "Occurrence Count": 1,
    }
    row.update(overrides)
    return row


def test_sync_resolves_site_code_via_raw_site_regex(app):
    with app.app_context():
        source_rows = [_source_row()]
        site_rows = [{"standard_code": "1234", "physical_location_name": "Site 1234"}]
        cache_repo = FakeCacheRepo()
        svc = ApeAlarmSyncService(
            FakeApeAlarmRepo(source_rows), cache_repo, FakeSiteCacheRepo(site_rows), FakeSiteLookupCacheRepo([]),
        )

        svc.sync()

        row = cache_repo.written[0]
        assert row["site_code"] == "1234"
        assert row["site_name"] == "Site 1234"


def test_sync_resolves_site_code_via_site_lookup_cache(app):
    with app.app_context():
        source_rows = [_source_row(**{"Raw Site": "NoDigitsHere", "Additional Info": "UIubLink=5555;"})]
        site_lookup_rows = [{"sran_id": None, "nodeb_id": 5555, "bts_id": None, "site_name": "YY7777"}]
        cache_repo = FakeCacheRepo()
        svc = ApeAlarmSyncService(
            FakeApeAlarmRepo(source_rows), cache_repo, FakeSiteCacheRepo([]), FakeSiteLookupCacheRepo(site_lookup_rows),
        )

        svc.sync()

        assert cache_repo.written[0]["site_code"] == "7777"


def test_sync_carries_through_alarm_fields(app):
    with app.app_context():
        source_rows = [_source_row(**{"Event Name": "Door Alarm", "Occurrence Count": 5})]
        cache_repo = FakeCacheRepo()
        svc = ApeAlarmSyncService(
            FakeApeAlarmRepo(source_rows), cache_repo, FakeSiteCacheRepo([]), FakeSiteLookupCacheRepo([]),
        )

        svc.sync()

        row = cache_repo.written[0]
        assert row["event_name"] == "Door Alarm"
        assert row["occurrence_count"] == 5


def test_sync_writes_empty_list_when_no_rows(app):
    with app.app_context():
        cache_repo = FakeCacheRepo()
        svc = ApeAlarmSyncService(
            FakeApeAlarmRepo([]), cache_repo, FakeSiteCacheRepo([]), FakeSiteLookupCacheRepo([]),
        )

        svc.sync()

        assert cache_repo.written == []
