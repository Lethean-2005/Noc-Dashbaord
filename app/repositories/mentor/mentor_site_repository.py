"""Read/write access to the local mentor_sites table — not a
Postgres/MSSQL sync cache. Holds site codes the user typed in or
uploaded via the Mentor Site page; never auto-dropped by init_cache_db().
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from flask import current_app

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
                (site_code, datetime.now(ZoneInfo(current_app.config["TIMEZONE"])).isoformat(timespec="seconds"), source),
            )
            conn.commit()
        finally:
            conn.close()

    def add_many(self, codes, source):
        """Save a validated batch atomically using one connection and commit."""
        timestamp = datetime.now(ZoneInfo(current_app.config["TIMEZONE"])).isoformat(timespec="seconds")
        conn = get_cache_conn()
        try:
            with conn:
                conn.executemany(
                    "INSERT INTO mentor_sites (site_code, added_at, source) VALUES (?, ?, ?) "
                    "ON CONFLICT(site_code) DO NOTHING",
                    [(code, timestamp, source) for code in codes],
                )
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
