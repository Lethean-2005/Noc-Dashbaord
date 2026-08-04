"""Data access for the site -> NMS vendor code lookup (object_227) on PostgreSQL."""
from app.database.connection import run_query


class NeNmsLookupRepository:
    def fetch_all(self):
        return run_query("ne_nms_lookup", "ne_nms_lookup")
