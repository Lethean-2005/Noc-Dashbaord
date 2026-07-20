"""Data access for reports."""
from app.database.connection import run_query


class ReportRepository:
    def fetch_reports(self, page=1, per_page=25):
        page = max(1, page)
        offset = (page - 1) * per_page
        return run_query("reports", "list", limit=per_page, offset=offset)
