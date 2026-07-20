"""Business logic for mentor session tracking.

Thin pass-through for now — see the note at the top of dashboard_service.py
for why that's fine.
"""
from app.repositories.mentor_repository import MentorRepository


class MentorService:
    def __init__(self, repository=None):
        self.repository = repository or MentorRepository()

    def list_sessions(self):
        """Upcoming + past mentor sessions (app/database/queries/mentor.sql: sessions)."""
        return self.repository.fetch_sessions()
