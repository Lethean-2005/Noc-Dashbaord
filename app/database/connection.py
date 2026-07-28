"""Database connection helpers and named SQL query loading.

Named queries live as plain .sql files under app/database/queries/<domain>.sql,
separated by `-- name: <query_name>` marker comments, so SQL stays out of Python code.
"""
from sqlalchemy import text

from app.database.sql_loader import load_queries
from app.extensions import db


def run_query(domain, name, **params):
    """Run a named query and return its rows as a list of dicts.

    On failure, rolls back the session before re-raising — SQLAlchemy
    leaves a failed transaction open otherwise, which poisons every
    subsequent query on the same session with "current transaction is
    aborted" even though that next query is perfectly valid on its own.
    This matters here because the background sync loops
    (app/services/incident/incident_scheduler.py) run several unrelated queries
    back-to-back inside one app_context — one slow query getting killed
    (e.g. by a Postgres replica-conflict cancellation) must not break the
    ones that run after it.
    """
    query = load_queries(domain)[name]
    try:
        result = db.session.execute(text(query), params)
        return [dict(row._mapping) for row in result]
    except Exception:
        db.session.rollback()
        raise
