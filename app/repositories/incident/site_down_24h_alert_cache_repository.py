"""Read/write access to the local site_down_24h_alert_cache table — not
a Postgres/MSSQL sync cache. This app's own dedup ledger for the Site
Down 24h Teams alert (app/services/incident/site_down_24h_alert_service.py):
one row per incident that's ever been down-alerted, recording when (and
whether) the matching restore-confirmation was sent too. Never
auto-dropped by init_cache_db() — see that function's own comment on
this table.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from flask import current_app

from app.database.cache import get_cache_conn


class SiteDown24hAlertCacheRepository:
    def already_down_alerted(self, incident_id):
        """Whether a down-alert has ever been sent for this incident —
        Stage 1's own dedup check."""
        conn = get_cache_conn()
        try:
            row = conn.execute(
                "SELECT 1 FROM site_down_24h_alert_cache WHERE incident_id = ?",
                (incident_id,),
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def mark_down_alerted(self, incident_id, site_code, incident_ref):
        """Stage 1 just sent the down-alert for this incident — insert
        its ledger row. `incident_ref` (the incident's own id) is
        stored here specifically so Stage 2 can still send
        the SAME ref value later, even once this incident has dropped
        out of the active incident_site_down cache entirely. ON
        CONFLICT DO NOTHING since Stage 1 only ever calls this once per
        incident (already_down_alerted() is checked first), but a
        second call is still a safe no-op, not a crash, if that check
        and this write ever race."""
        conn = get_cache_conn()
        try:
            conn.execute(
                "INSERT INTO site_down_24h_alert_cache "
                "(incident_id, site_code, incident_ref, down_alert_sent_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(incident_id) DO NOTHING",
                (
                    incident_id,
                    site_code,
                    incident_ref,
                    datetime.now(ZoneInfo(current_app.config["TIMEZONE"])).isoformat(timespec="seconds"),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def pending_restore(self):
        """Every (incident_id, incident_ref) pair that's been
        down-alerted but not yet restore-confirmed — Stage 2's own scan
        list. incident_ref travels with it so Stage 2 can tag its own
        post with the same correlation value Stage 1 used, without
        needing to re-derive it from a cache the incident may have
        already dropped out of."""
        conn = get_cache_conn()
        try:
            rows = conn.execute(
                "SELECT incident_id, incident_ref FROM site_down_24h_alert_cache "
                "WHERE restore_alert_sent_at IS NULL"
            ).fetchall()
            return [(r[0], r[1]) for r in rows]
        finally:
            conn.close()

    def mark_restore_alerted(self, incident_id):
        """Stage 2 just sent the restore-confirmation for this
        incident."""
        conn = get_cache_conn()
        try:
            conn.execute(
                "UPDATE site_down_24h_alert_cache SET restore_alert_sent_at = ? "
                "WHERE incident_id = ?",
                (
                    datetime.now(ZoneInfo(current_app.config["TIMEZONE"])).isoformat(timespec="seconds"),
                    incident_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()
