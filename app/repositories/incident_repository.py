"""Data access for the Incident table (object_322) on PostgreSQL."""
from app.database.connection import run_query


class IncidentRepository:
    def fetch_by_status(self):
        """Full joined drilldown detail (Site/INC-WO/Province/District/
        Commune/NMS) for every Incident currently 'new' or 'in_progress' —
        see app/database/queries/incident_by_status.sql."""
        return run_query("incident_by_status", "incident_by_status")

    def fetch_vip_customer_complaint(self):
        """Every new, not-yet-worked customer complaint raised by a VIP
        customer — see app/database/queries/vip_customer_complaint.sql."""
        return run_query("vip_customer_complaint", "vip_customer_complaint")

    def fetch_site_down(self):
        """Every Site Down incident not yet Closed whose alarm hasn't
        cleared — see app/database/queries/site_down.sql. Used both live
        (by app/services/telegram_alert.py, which only runs once every few
        hours) and cached (by app/services/incident_sync_service.py, behind
        the "Incident Site Down" card on the Custom Dashboard)."""
        return run_query("site_down", "site_down")
