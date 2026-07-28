"""Data access for site_lookup_mv (sran_id/nodeb_id/bts_id -> site_name) on PostgreSQL."""
from app.database.connection import run_query


class SiteLookupRepository:
    def fetch_all(self):
        """See app/database/queries/site_lookup.sql."""
        return run_query("site_lookup", "site_lookup")
