"""Data access for the MSSQL-backed alarm cards (ISP POP / EZE / TCT / IT NODE)."""
from app.database.mssql import run_mssql_query, run_mssql_write


class AlarmRepository:
    def fetch_isp_pop_active(self):
        return run_mssql_query("alarms", "isp_pop_alarm_cache")

    def fetch_eze_active(self):
        return run_mssql_query("alarms", "eze_alarm_cache")

    def fetch_tct_active(self):
        return run_mssql_query("alarms", "tct_alarm_cache")

    def fetch_it_node_active(self):
        return run_mssql_query("alarms", "it_node_alarm_cache")

    def acknowledge_note(self, row_id, note, username):
        """Writes `note` to this row's NOTE column; sets ACK+AB if this is
        the row's first-ever acknowledge (ACK was NULL), else sets MD+MB —
        see alarms.sql's acknowledge_note query for the exact logic.
        Matched by `row_id` (TBL_PPD.ID, a uniqueidentifier) — NOT RTID,
        which was confirmed live to repeat across unrelated rows (see
        alarms.sql's acknowledge_note query header). Returns the number of
        rows affected (0 means no row matched this id — e.g. the alarm
        cleared between page load and submit)."""
        return run_mssql_write("alarms", "acknowledge_note", (note, username, username, row_id))

    def clear_alarm(self, row_id, username):
        """Manually marks the row as cleared (Status=0, RestoredTime=now)
        — see alarms.sql's clear_alarm query for the exact logic. Matched
        by row_id (TBL_PPD.ID), same reasoning as acknowledge_note().
        Returns the number of rows affected (0 means this id no longer
        matches any still-open alarm — e.g. it already cleared on its own
        between page load and submit, or it's stale)."""
        return run_mssql_write("alarms", "clear_alarm", (username, row_id))
