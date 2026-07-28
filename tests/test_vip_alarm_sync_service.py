"""Tests for VipAlarmSyncService — rebuilt to derive vip_alarm entirely
from the already-synced ape_alarm cache (filtered to VIP/VVIP sites)
instead of running its own independent Postgres query. ape_alarm already
resolves Site Code locally (app/utils/get_processed_site.py), so this benefits from
that for free. These tests lock in that VIP/VVIP filtering and field
carry-through behave correctly for this purely local derivation.
"""
from app.services.vip.vip_alarm_sync_service import VipAlarmSyncService


class FakeApeAlarmRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self, table):
        return self._rows


class FakeSiteRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self, table):
        return self._rows


class FakeCacheRepo:
    def __init__(self):
        self.written = None

    def replace_all(self, table, rows):
        self.written = rows


def _ape_alarm_row(site_code, **overrides):
    row = {
        "occurred_at": "2026-01-01 00:00:00",
        "event_name": "Main Failure",
        "additional_info": "",
        "nms": "ZTE",
        "technology": "Power",
        "site_code": site_code,
        "site_name": f"Site {site_code}",
        "occurrence_count": 1,
    }
    row.update(overrides)
    return row


def test_sync_keeps_only_vip_and_vvip_sites(app):
    with app.app_context():
        ape_alarm_rows = [
            _ape_alarm_row("VIP1"),
            _ape_alarm_row("VVIP1"),
            _ape_alarm_row("NORMAL1"),
            _ape_alarm_row("UNKNOWN1"),  # not in site_cache at all
        ]
        site_rows = [
            {"standard_code": "VIP1", "site_strategic_type": "VIP"},
            {"standard_code": "VVIP1", "site_strategic_type": "VVIP"},
            {"standard_code": "NORMAL1", "site_strategic_type": "Normal"},
        ]
        cache_repo = FakeCacheRepo()
        svc = VipAlarmSyncService(FakeApeAlarmRepo(ape_alarm_rows), cache_repo, FakeSiteRepo(site_rows))

        svc.sync()

        kept_codes = {row["site_code"] for row in cache_repo.written}
        assert kept_codes == {"VIP1", "VVIP1"}


def test_sync_carries_through_ape_alarm_fields_and_adds_strategic_type(app):
    with app.app_context():
        ape_alarm_rows = [_ape_alarm_row("VIP1", event_name="Door Alarm", occurrence_count=5)]
        site_rows = [{"standard_code": "VIP1", "site_strategic_type": "VIP"}]
        cache_repo = FakeCacheRepo()
        svc = VipAlarmSyncService(FakeApeAlarmRepo(ape_alarm_rows), cache_repo, FakeSiteRepo(site_rows))

        svc.sync()

        row = cache_repo.written[0]
        assert row["event_name"] == "Door Alarm"
        assert row["occurrence_count"] == 5
        assert row["site_strategic_type"] == "VIP"


def test_sync_writes_empty_list_when_no_vip_sites_match(app):
    with app.app_context():
        ape_alarm_rows = [_ape_alarm_row("NORMAL1")]
        site_rows = [{"standard_code": "NORMAL1", "site_strategic_type": "Normal"}]
        cache_repo = FakeCacheRepo()
        svc = VipAlarmSyncService(FakeApeAlarmRepo(ape_alarm_rows), cache_repo, FakeSiteRepo(site_rows))

        svc.sync()

        assert cache_repo.written == []
