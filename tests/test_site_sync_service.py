"""Tests for SiteSyncService.sync_technology() — syncs the per-site
technology inventory (object_227, 2g/3g/4g/5g) locally so
AlarmCompletelySiteDownService can know a site's full technology footprint
without querying Postgres itself. object_227 is confirmed prone to
"conflict with recovery" (see incident_sync_service.py's module docstring),
so this goes through retry_fetch() same as every other object_227-touching
sync.
"""
from unittest.mock import patch

from app.services.site.site_sync_service import SiteSyncService


class FakeSiteTechnologyRepo:
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


def test_sync_technology_skips_cache_write_when_query_fails_every_retry():
    class FailingRepo:
        def fetch_all(self):
            raise RuntimeError("conflict with recovery")

    cache_repo = FakeCacheRepo()
    svc = SiteSyncService(
        site_technology_repository=FailingRepo(),
        site_technology_cache_repository=cache_repo,
    )

    with patch("app.services.postgres_sync_utils.time.sleep"):
        svc.sync_technology()

    assert cache_repo.written is None
