"""Data access for VIP/VVIP, On Air Site master data (TBL_SITE joined to
TBL_NE) on MSSQL."""

from app.database.mssql import run_mssql_query


class VipSiteRepository:
    def fetch_vip_sites(self):
        return run_mssql_query("vip_site_cache", "vip_site_cache")
