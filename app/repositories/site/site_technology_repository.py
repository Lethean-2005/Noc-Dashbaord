"""Data access for the per-site technology inventory (object_227) on PostgreSQL."""
from app.database.connection import run_query


class SiteTechnologyRepository:
    def fetch_all(self):
        return run_query("site_technology_cache", "site_technology_cache")
