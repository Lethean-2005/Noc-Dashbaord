"""Data access for the MSSQL-backed alarm cards (ISP POP / EZE / TCT / IT NODE)."""
from app.database.mssql import run_mssql_query


class AlarmRepository:
    def fetch_isp_pop_active(self):
        return run_mssql_query("alarms", "isp_pop_active")

    def fetch_eze_active(self):
        return run_mssql_query("alarms", "eze_active")

    def fetch_tct_active(self):
        return run_mssql_query("alarms", "tct_active")

    def fetch_it_node_active(self):
        return run_mssql_query("alarms", "it_node_active")
