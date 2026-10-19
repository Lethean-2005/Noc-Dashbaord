"""Data access for the platform's Counterparty catalog (object_170) on PostgreSQL."""

from app.database.connection import run_query


class CounterpartyRepository:
    def fetch_all(self):
        return run_query("counterparty", "counterparty")
