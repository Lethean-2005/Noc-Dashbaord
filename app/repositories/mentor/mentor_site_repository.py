"""Read/write access to the local mentor_sites table (instance/localstorage.db)
— NOT a Postgres/MSSQL sync cache like every other repository in this
project. This table holds site codes the user has explicitly typed in or
uploaded via the Mentor Site page (app/routes/mentor.py); see
app/database/cache.py's init_cache_db() for why it's never auto-dropped.
"""
from datetime import datetime

from app.database.cache import get_cache_conn


class MentorSiteRepository:
    def add(self, site_code, source):
        """Insert `site_code` if it isn't already configured (a repeat add
        of the same code is a silent no-op, not an error)."""
        conn = get_cache_conn()
        try:
            conn.execute(
                "INSERT INTO mentor_sites (site_code, added_at, source) VALUES (?, ?, ?) "
                "ON CONFLICT(site_code) DO NOTHING",
                (site_code, datetime.now().isoformat(timespec="seconds"), source),
            )
            conn.commit()
        finally:
            conn.close()

    def fetch_all(self):
        conn = get_cache_conn()
        try:
            rows = conn.execute("SELECT * FROM mentor_sites ORDER BY added_at DESC").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def remove(self, site_code):
        conn = get_cache_conn()
        try:
            conn.execute("DELETE FROM mentor_sites WHERE site_code = ?", (site_code,))
            conn.commit()
        finally:
            conn.close()

    def clear_all(self):
        conn = get_cache_conn()
        try:
            conn.execute("DELETE FROM mentor_sites")
            conn.commit()
        finally:
            conn.close()
