"""MSSQL connection helper — alarm source for the ISP POP / EZE / TCT cards.

Standalone from the Postgres/SQLAlchemy layer in app/database/connection.py:
these alarms live on a separate MSSQL server (noc.TBL_PPD) reached via pymssql,
so they get their own connection + named-query loader following the same
`-- name:` .sql convention as the Postgres queries.
"""
import time

import pymssql
from flask import current_app

from app.database.sql_loader import load_queries

_MAX_RETRIES = 3
_RETRY_DELAY = 1  # seconds between retries


def _connect() -> pymssql.Connection:
    cfg = current_app.config
    last_error = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return pymssql.connect(
                server=cfg["MSSQL_HOST"],
                database=cfg["MSSQL_DATABASE"],
                user=cfg["MSSQL_USER"],
                password=cfg["MSSQL_PASSWORD"],
                login_timeout=5,
                timeout=15,
            )
        except pymssql.OperationalError as e:
            last_error = e
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY * attempt)
    raise last_error


def run_mssql_query(domain, name):
    """Execute a named MSSQL query and return rows as a list of dicts."""
    query = load_queries(domain)[name]
    conn = _connect()
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(query)
        return cur.fetchall()
    finally:
        conn.close()


def run_mssql_write(domain, name, params):
    """Execute a named, parameterized MSSQL write (INSERT/UPDATE) and commit.
    `params` is a tuple bound to the query's %s placeholders (pymssql's
    paramstyle) — never interpolated into the query text, so this is safe
    against injection the same way run_mssql_query()'s read-only queries
    already are by having no user input in them at all. Returns the number
    of rows affected."""
    query = load_queries(domain)[name]
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
