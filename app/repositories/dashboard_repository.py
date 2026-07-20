"""Data access for dashboard metrics."""
from app.database.connection import run_query


class DashboardRepository:
    def fetch_summary(self):
        return run_query("dashboard", "summary")

    def fetch_overview_metrics(self):
        return run_query("dashboard", "overview_metrics")
