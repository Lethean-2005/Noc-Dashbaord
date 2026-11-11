"""Tests for MssqlSiteOnairSyncService — syncs TBL_SITE joined to TBL_NE
(On Air sites, with VENDOR) locally into mssql_site_onair, independent
from site_sync_service.py's Postgres-backed site_cache.
"""

from app.services.site.mssql_site_onair_sync_service import MssqlSiteOnairSyncService


class FakeMssqlSiteOnairRepo:
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
    source_rows = [
        {
            "SITE_CODE": "0001",
            "SITE_NAME": "MOBITEL",
            "STATUS": "On Air",
            "PROVINCE": "Phnom Penh",
            "DISTRICT": "Doun Penh",
            "VILLAGE": None,
            "LAT": 11.5563,
            "LONG": 104.925,
            "BTS_ROOM": "Indoor",
            "LINK_TYPE": "H-R",
            "SITE_GRADE": "Data center",
            "SITE_TYPE": "RT",
            "LOCATION": "Head Office. Stree Preah Sohanouk. PP",
            "VENDOR": "Huawei",
        }
    ]
    cache_repo = FakeCacheRepo()
    svc = MssqlSiteOnairSyncService(FakeMssqlSiteOnairRepo(source_rows), cache_repo)

    result = svc.sync()

    assert result == 1
    assert cache_repo.written == [
        {
            "site_code": "0001",
            "site_name": "MOBITEL",
            "status": "On Air",
            "province": "Phnom Penh",
            "district": "Doun Penh",
            "village": "",
            "lat": 11.5563,
            "long": 104.925,
            "bts_room": "Indoor",
            "link_type": "H-R",
            "site_grade": "Data center",
            "site_type": "RT",
            "location": "Head Office. Stree Preah Sohanouk. PP",
            "vendor": "Huawei",
        }
    ]


def test_sync_dedupes_site_code_when_source_has_multiple_ne_rows():
    # Real bug: mssql_site.sql's own SELECT DISTINCT only guarantees one
    # row per SITE_CODE when every NE agrees on ALL selected columns, not
    # just VENDOR (its own comment's stated assumption) — a site with 2+
    # NE records whose BTS_ROOM/LINK_TYPE/LAT/LONG differ (confirmed live:
    # site 8185, Indoor/MW NE + Outdoor/FO NE, same vendor) produces 2
    # distinct rows for the same site_code, which collided on the cache
    # table's UNIQUE constraint and failed the ENTIRE write, not just that
    # one site — every sync attempt since, frozen on stale data.
    source_rows = [
        {"SITE_CODE": "8185", "SITE_NAME": "TB115", "BTS_ROOM": "Indoor", "VENDOR": "Nokia"},
        {"SITE_CODE": "8185", "SITE_NAME": "TB115", "BTS_ROOM": "Outdoor", "VENDOR": "Nokia"},
        {"SITE_CODE": "0001", "SITE_NAME": "MOBITEL", "BTS_ROOM": "Indoor", "VENDOR": "Huawei"},
    ]
    cache_repo = FakeCacheRepo()
    svc = MssqlSiteOnairSyncService(FakeMssqlSiteOnairRepo(source_rows), cache_repo)

    result = svc.sync()

    assert result == 2
    assert [r["site_code"] for r in cache_repo.written] == ["8185", "0001"]
    # First-seen wins — the Indoor NE's own fields, not the Outdoor one's.
    assert cache_repo.written[0]["bts_room"] == "Indoor"


def test_sync_writes_empty_list_when_no_rows():
    cache_repo = FakeCacheRepo()
    svc = MssqlSiteOnairSyncService(FakeMssqlSiteOnairRepo([]), cache_repo)

    result = svc.sync()

    assert result == 0
    assert cache_repo.written == []


def test_sync_returns_none_when_mssql_query_fails():
    class FailingRepo:
        def fetch_all(self):
            raise RuntimeError("connection lost")

    cache_repo = FakeCacheRepo()
    svc = MssqlSiteOnairSyncService(FailingRepo(), cache_repo)

    result = svc.sync()

    assert result is None
    assert cache_repo.written is None


def test_sync_returns_none_when_cache_write_fails():
    class FailingCacheRepo:
        def replace_all(self, table, rows):
            raise RuntimeError("disk full")

    svc = MssqlSiteOnairSyncService(FakeMssqlSiteOnairRepo([]), FailingCacheRepo())

    result = svc.sync()

    assert result is None
