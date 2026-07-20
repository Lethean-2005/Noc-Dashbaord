"""Data access for mentor sessions."""
from app.database.connection import run_query


class MentorRepository:
    def fetch_sessions(self):
        return run_query("mentor", "sessions")
