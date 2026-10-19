"""Data access for POP master data (noc.TBL_POP) on MSSQL."""

from app.database.mssql import run_mssql_query


class PopRepository:
    def fetch_pops(self):
        return run_mssql_query("pop", "pop_cache")
