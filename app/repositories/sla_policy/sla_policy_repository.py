"""Data access for the SLA policy/threshold table (object_327) on PostgreSQL."""

from app.database.connection import run_query


class SlaPolicyRepository:
    def fetch_all(self):
        """Every active SLA rule — see sla_policy.sql."""
        return run_query("sla_policy", "sla_policy")
