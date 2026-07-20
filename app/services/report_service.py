"""Business logic for report generation and listing.

Thin pass-through for now — see the note at the top of dashboard_service.py
for why that's fine.
"""
from app.repositories.report_repository import ReportRepository


class ReportService:
    def __init__(self, repository=None):
        self.repository = repository or ReportRepository()

    def list_reports(self, page=1, per_page=25):
        """One page of generated reports (app/database/queries/reports.sql: list)."""
        return self.repository.fetch_reports(page=page, per_page=per_page)
