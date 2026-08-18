"""Data access for the INC-WO table (object_324) on PostgreSQL."""

from app.database.connection import run_query


class IncWoRepository:
    def fetch_by_status(self):
        """Full joined drilldown detail (Site/Incident/Province/District/
        Commune/NMS) for every INC-WO not yet 'closed' — see
        app/database/queries/inc_wo_by_status.sql."""
        return run_query("inc_wo_by_status", "inc_wo_by_status")

    def fetch_site_down(self):
        """Same join as fetch_by_status(), narrowed to category='site_down'
        work orders not yet resolved/closed — see
        app/database/queries/inc_wo_site_down.sql."""
        return run_query("inc_wo_site_down", "inc_wo_site_down")

    def fetch_resolved(self):
        """INC-WO that are Resolved while their parent Incident is still
        In-Progress overall — see app/database/queries/inc_wo_resolved.sql."""
        return run_query("inc_wo_resolved", "inc_wo_resolved")

    def fetch_category_power(self):
        """Same join as fetch_by_status(), narrowed to category='power'
        work orders not yet resolved/closed — see
        app/database/queries/inc_wo_category_power.sql."""
        return run_query("inc_wo_category_power", "inc_wo_category_power")
