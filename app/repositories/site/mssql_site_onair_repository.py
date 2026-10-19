"""Data access for On-Air site master data (TBL_SITE joined to TBL_NE) on
MSSQL. See app/database/queries/mssql_site.sql."""

from app.database.mssql import run_mssql_query


class MssqlSiteOnairRepository:
    def fetch_all(self):
        return run_mssql_query("mssql_site", "site_onair")
