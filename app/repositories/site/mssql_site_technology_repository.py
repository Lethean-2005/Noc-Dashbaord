"""Data access for the per-site radio technology inventory (TBL_NE) on
MSSQL. See app/database/queries/mssql_site_technology.sql."""

from app.database.mssql import run_mssql_query


class MssqlSiteTechnologyRepository:
    def fetch_all(self):
        return run_mssql_query("mssql_site_technology", "site_technology")
