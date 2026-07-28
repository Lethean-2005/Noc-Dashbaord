"""Business logic for reading the vip_incident_alarm cache.

Reads from the local cache (instance/localstorage.db) that
app/services/vip/vip_incident_alarm_scheduler.py keeps rebuilt (a purely local
join of vip_alarm/incident_by_status/site_cache — see
app/services/vip/vip_incident_alarm_sync_service.py). Outage(min) is computed
here, at read time, instead of being stored — same reasoning as
app/services/alarm/alarm_service.py's _with_outage(): it's a time-since-now
value that goes stale the instant it's written, so storing it would just
be wrong the moment the next request comes in.
"""
from app.repositories.vip.vip_incident_alarm_cache_repository import VipIncidentAlarmCacheRepository
from app.utils.datetime import elapsed_minutes

_TABLE = "vip_incident_alarm"


class VipIncidentAlarmService:
    def __init__(self, cache_repository=None):
        self.cache_repository = cache_repository or VipIncidentAlarmCacheRepository()

    def get_details(self):
        """Every cached VIP/VVIP Incident+alarm row, with outage_min filled
        in (minutes since Occurred At)."""
        rows = self.cache_repository.fetch_all(_TABLE)
        for r in rows:
            r["outage_min"] = elapsed_minutes(r.get("occurred_at"))
        return rows
