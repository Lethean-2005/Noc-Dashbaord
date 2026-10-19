"""Data access for the site-level actual RAN vendor field (object_160) on PostgreSQL."""

from app.database.connection import run_query


class SiteRanVendorRepository:
    def fetch_all(self):
        return run_query("site_ran_vendor", "site_ran_vendor")
