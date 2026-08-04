"""Data access for the Site table (object_160) on PostgreSQL."""
from app.database.connection import run_query


class SiteRepository:
    def fetch_all(self):
        return run_query("site_cache", "site_cache")
