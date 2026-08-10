"""Data access for the broader NE/connectivity alarm feed (object_138) on PostgreSQL."""

from app.database.connection import run_query


class ApeAlarmRepository:
    def fetch_active(self):
        """VVIP/Mentor/RAN alarm types (NodeB out of service, CSL Fault,
        Main Failure, Low DC Voltage, DG on, etc.) currently Opened, deduped
        to one row per (site, event_name) — raw `site`/`additional_info`
        only, Site Code is resolved afterward in Python — see
        app/database/queries/ape_alarm.sql."""
        return run_query("ape_alarm", "ape_alarm")
