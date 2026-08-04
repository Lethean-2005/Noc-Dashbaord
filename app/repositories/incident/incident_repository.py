"""Data access for the Incident table (object_322) on PostgreSQL."""
from app.database.connection import run_query


class IncidentRepository:
    def fetch_by_status(self):
        """Full joined drilldown detail (Site/INC-WO/Province/District/
        Commune/NMS) for every Incident currently 'new' or 'in_progress' —
        see app/database/queries/incident_by_status.sql."""
        return run_query("incident_by_status", "incident_by_status")

    def fetch_site_down(self):
        """Every Site Down incident not yet Closed whose alarm hasn't
        cleared — see app/database/queries/incident_site_down.sql. Used both live
        (by app/services/telegram/telegram_alert.py, which only runs once every few
        hours) and cached (by app/services/incident/incident_sync_service.py, behind
        the "Incident Site Down" card on the Custom Dashboard)."""
        return run_query("incident_site_down", "incident_site_down")

    def fetch_vip_incident_status(self):
        """Every not-yet-Closed Incident (including Resolved) at a VIP/VVIP
        site — see app/database/queries/vip_incident_status.sql. Used only
        by VipAlarmService's enrichment."""
        return run_query("vip_incident_status", "vip_incident_status")

    def fetch_wo_by_incident_ids(self, incident_ids):
        """Every INC-WO belonging to the given batch of incident numeric
        ids, in one round-trip — see
        app/database/queries/inc_wo_by_incident_ids.sql. Returns [] without
        a Postgres call when incident_ids is empty (ANY() on an empty list
        is valid SQL but a pointless round-trip)."""
        if not incident_ids:
            return []
        return run_query("inc_wo_by_incident_ids", "inc_wo_by_incident_ids", incident_ids=list(incident_ids))
