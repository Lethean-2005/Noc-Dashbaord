"""Data access for the MSSQL-backed alarm cards (ISP POP / EZE / TCT / IT NODE)."""

from app.database.mssql import (
    run_mssql_query,
    run_mssql_query_params,
    run_mssql_write,
    run_mssql_write_returning,
)


class AlarmRepository:
    def fetch_isp_pop_active(self):
        return run_mssql_query("alarms", "isp_pop_alarm_cache")

    def fetch_eze_active(self):
        return run_mssql_query("alarms", "eze_alarm_cache")

    def fetch_tct_active(self):
        return run_mssql_query("alarms", "tct_alarm_cache")

    def fetch_it_node_active(self):
        return run_mssql_query("alarms", "it_node_alarm_cache")

    def fetch_congestion_history(self, since):
        """`since` — a 'YYYY-MM-DD' date string — every Congestion
        (bandwidth+congestion) alarm with DownTime on/after it, active
        or long since cleared. See alarms.sql's own congestion_history
        query for why this needs its own, non-active-only query."""
        return run_mssql_query_params("alarms", "congestion_history", (since,))

    def acknowledge_note(self, row_id, note, username):
        """Writes `note`; sets ACK+AB on first acknowledge, else MD+MB —
        see alarms.sql's acknowledge_note query. Matched by row_id
        (TBL_PPD.ID), not RTID (confirmed to repeat across unrelated
        rows). `row_id` appears twice in params — once for the UPDATE's
        own WHERE, once for the trailing SELECT's — since this is one
        query text, one round trip, not two calls. Returns the row's
        final {NOTE, ACK, AB, MD, MB} dict (already as MSSQL wrote them,
        not re-derived in Python), or None if row_id matched nothing at
        all (the row was deleted — genuinely rare, unlike clear_alarm()'s
        own much more common "already cleared" case)."""
        rows = run_mssql_write_returning(
            "alarms", "acknowledge_note", (note, username, username, row_id, row_id)
        )
        return rows[0] if rows else None

    def clear_alarm(self, row_id, username):
        """Manually marks the row cleared (Status=0, RestoredTime=now).
        Matched by row_id, same as acknowledge_note(). Returns rows
        affected — 0 means the alarm already cleared or is stale."""
        return run_mssql_write("alarms", "clear_alarm", (username, row_id))
