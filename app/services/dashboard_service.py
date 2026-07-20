"""Business logic for the dashboard views.

Currently a thin pass-through: there's no extra shaping/rules to apply
here yet, so each method just forwards to the matching repository query.
That's fine — a service is allowed to be simple. Add logic here (not in
the route or repository) the moment there's a rule to apply, e.g.
"only show reports from the last 30 days".
"""
from app.repositories.dashboard_repository import DashboardRepository


class DashboardService:
    def __init__(self, repository=None):
        self.repository = repository or DashboardRepository()

    def get_summary(self):
        """Total/open incident counts (app/database/queries/dashboard.sql: summary)."""
        return self.repository.fetch_summary()

    def get_overview_metrics(self):
        """Incident count per day, most recent 30 days, for the overview chart."""
        return self.repository.fetch_overview_metrics()
