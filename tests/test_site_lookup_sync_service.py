"""Tests for SiteLookupSyncService — syncs site_lookup_mv (sran_id/nodeb_id/
bts_id -> site_name) locally so app/utils/get_processed_site.py can resolve Site Code
in Python instead of Postgres calling get_processed_site() per row.
"""
from unittest.mock import patch

from app.services.site.site_lookup_sync_service import SiteLookupSyncService


class FakeSiteLookupRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self):
        return self._rows


class FakeCacheRepo:
    def __init__(self):
        self.written = None

    def replace_all(self, table, rows):
        self.written = rows


def test_sync_writes_normalized_rows():
    source_rows = [{"sran_id": 1, "nodeb_id": 2, "bts_id": 3, "site_name": "AB1111", "extra": "ignored"}]
    cache_repo = FakeCacheRepo()
    svc = SiteLookupSyncService(FakeSiteLookupRepo(source_rows), cache_repo)

    svc.sync()

    assert cache_repo.written == [{"sran_id": 1, "nodeb_id": 2, "bts_id": 3, "site_name": "AB1111"}]


def test_sync_writes_empty_list_when_no_rows():
    cache_repo = FakeCacheRepo()
    svc = SiteLookupSyncService(FakeSiteLookupRepo([]), cache_repo)

    svc.sync()

    assert cache_repo.written == []


def test_sync_skips_cache_write_when_query_fails_every_retry():
    class FailingRepo:
        def fetch_all(self):
            raise RuntimeError("conflict with recovery")

    cache_repo = FakeCacheRepo()
    svc = SiteLookupSyncService(FailingRepo(), cache_repo)

    with patch("app.services.postgres_sync_utils.time.sleep"):
        svc.sync()

    assert cache_repo.written is None
