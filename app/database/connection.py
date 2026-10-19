"""Database connection helpers and named SQL query loading.

Named queries live as plain .sql files under app/database/queries/<domain>.sql,
separated by `-- name: <query_name>` marker comments, so SQL stays out of Python code.
"""

from sqlalchemy import text

from app.database.sql_loader import load_queries
from app.extensions import db


def run_query(domain, name, **params):
    """Run a named query and return its rows as a list of dicts.

    Rolls back the session on failure before re-raising — otherwise
    SQLAlchemy leaves the transaction poisoned ("current transaction is
    aborted") for every later query on the same session, which matters
    since background sync loops run several unrelated queries back-to-back."""
    query = load_queries(domain)[name]
    try:
        result = db.session.execute(text(query), params)
        return [dict(row._mapping) for row in result]
    except Exception:
        db.session.rollback()
        raise
