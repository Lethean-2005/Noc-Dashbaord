"""Tests for SiteSyncService.sync_technology() (MSSQL TBL_NE) and
sync_ne_nms() (Postgres object_227, confirmed prone to "conflict with
recovery" — see incident_sync_service.py's module docstring — so that
one still goes through retry_fetch()).
"""

from unittest.mock import patch

from app.services.site.site_sync_service import SiteSyncService


class FakeSiteTechnologyRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self):
        return self._rows


class FakeSiteRanNameRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self):
        return self._rows


class FakeNeNmsLookupRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self):
        return self._rows


class FakeCacheRepo:
    def __init__(self):
        self.written = None

    def replace_all(self, table, rows):
        self.written = rows


def test_sync_technology_normalizes_quoted_column_aliases():
    source_rows = [{"Site Code": "AB1111", "Technology": "4g"}]
    cache_repo = FakeCacheRepo()
    svc = SiteSyncService(
        site_technology_repository=FakeSiteTechnologyRepo(source_rows),
        site_technology_cache_repository=cache_repo,
    )

    svc.sync_technology()

    assert cache_repo.written == [{"site_code": "AB1111", "technology": "4g"}]


def test_sync_technology_writes_empty_list_when_no_rows():
    cache_repo = FakeCacheRepo()
    svc = SiteSyncService(
        site_technology_repository=FakeSiteTechnologyRepo([]),
        site_technology_cache_repository=cache_repo,
    )

    svc.sync_technology()

    assert cache_repo.written == []


def test_sync_technology_skips_cache_write_when_query_fails():
    class FailingRepo:
        def fetch_all(self):
            raise RuntimeError("MSSQL connection failed")

    cache_repo = FakeCacheRepo()
    svc = SiteSyncService(
        site_technology_repository=FailingRepo(),
        site_technology_cache_repository=cache_repo,
    )

    svc.sync_technology()

    assert cache_repo.written is None


def test_sync_ran_name_normalizes_quoted_column_aliases():
    source_rows = [{"Site Code": "AB1111", "RAN Name": "NSiKCH1002"}]
    cache_repo = FakeCacheRepo()
    svc = SiteSyncService(
        site_ran_name_repository=FakeSiteRanNameRepo(source_rows),
        site_ran_name_cache_repository=cache_repo,
    )

    svc.sync_ran_name()

    assert cache_repo.written == [{"site_code": "AB1111", "ran_name": "NSiKCH1002"}]


def test_sync_ran_name_keeps_first_seen_row_per_site_code():
    # A site can have >1 NE row with a different SRAN value (confirmed
    # live: 15 of ~3772 sites) — first one wins, not an error, not both.
    source_rows = [
        {"Site Code": "AB1111", "RAN Name": "NSiKCH1002"},
        {"Site Code": "AB1111", "RAN Name": "NSoKCH1002-2"},
    ]
    cache_repo = FakeCacheRepo()
    svc = SiteSyncService(
        site_ran_name_repository=FakeSiteRanNameRepo(source_rows),
        site_ran_name_cache_repository=cache_repo,
    )

    svc.sync_ran_name()

    assert cache_repo.written == [{"site_code": "AB1111", "ran_name": "NSiKCH1002"}]


def test_sync_ran_name_skips_cache_write_when_query_fails():
    class FailingRepo:
        def fetch_all(self):
            raise RuntimeError("MSSQL connection failed")

    cache_repo = FakeCacheRepo()
    svc = SiteSyncService(
        site_ran_name_repository=FailingRepo(),
        site_ran_name_cache_repository=cache_repo,
    )

    svc.sync_ran_name()

    assert cache_repo.written is None


def test_sync_ne_nms_normalizes_quoted_column_aliases():
    source_rows = [{"Site Code": "AB1111", "NMS Code": "7"}]
    cache_repo = FakeCacheRepo()
    svc = SiteSyncService(
        ne_nms_lookup_repository=FakeNeNmsLookupRepo(source_rows),
        ne_nms_lookup_cache_repository=cache_repo,
    )

    svc.sync_ne_nms()

    assert cache_repo.written == [{"site_code": "AB1111", "nms_code": "7"}]


def test_sync_ne_nms_writes_empty_list_when_no_rows():
    cache_repo = FakeCacheRepo()
    svc = SiteSyncService(
        ne_nms_lookup_repository=FakeNeNmsLookupRepo([]),
        ne_nms_lookup_cache_repository=cache_repo,
    )

    svc.sync_ne_nms()

    assert cache_repo.written == []


def test_sync_ne_nms_skips_cache_write_when_query_fails_every_retry():
    class FailingRepo:
        def fetch_all(self):
            raise RuntimeError("conflict with recovery")

    cache_repo = FakeCacheRepo()
    svc = SiteSyncService(
        ne_nms_lookup_repository=FailingRepo(),
        ne_nms_lookup_cache_repository=cache_repo,
    )

    with patch("app.services.postgres_sync_utils.time.sleep"):
        svc.sync_ne_nms()

    assert cache_repo.written is None
