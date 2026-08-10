"""Data access for VIP/VVIP Site master data (SITE_INFO) on MSSQL."""

from app.database.mssql import run_mssql_query


class VipSiteRepository:
    def fetch_vip_sites(self):
        return run_mssql_query("vip_site_cache", "vip_site_cache")
