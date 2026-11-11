"""Data access for the per-site RAN/SRAN baseband name (TBL_NE) on
MSSQL. See app/database/queries/mssql_site_ran_name.sql."""

from app.database.mssql import run_mssql_query


class MssqlSiteRanNameRepository:
    def fetch_all(self):
        return run_mssql_query("mssql_site_ran_name", "site_ran_name")
