"""Shared MSSQL connection helper — used by the ISP POP / EZE / TCT alarm
cards, the Partner Contact page, and the MSSQL Site On-Air cache, the
domains backed by MSSQL rather than Postgres.

Standalone from the Postgres/SQLAlchemy layer in connection.py: reached
via pymssql, with its own connection + named-query loader following the
same `-- name:` .sql convention.
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


def run_mssql_query_params(domain, name, params):
    """Like run_mssql_query(), but for a query with %s placeholders —
    `params` is bound safely, never interpolated into the query text."""
    query = load_queries(domain)[name]
    conn = _connect()
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(query, params)
        return cur.fetchall()
    finally:
        conn.close()


def run_mssql_write(domain, name, params):
    """Execute a named, parameterized MSSQL write (INSERT/UPDATE) and
    commit. `params` binds to the query's %s placeholders, never
    interpolated into the query text. Returns rows affected."""
    query = load_queries(domain)[name]
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def run_mssql_write_returning(domain, name, params):
    """Like run_mssql_write(), but for a query whose last statement is a
    SELECT/OUTPUT handing back a value (e.g. a server-generated
    NEWID()). Returns the result rows, committing after they're fetched."""
    query = load_queries(domain)[name]
    conn = _connect()
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(query, params)
        rows = cur.fetchall()
        conn.commit()
        return rows
    finally:
        conn.close()


def run_mssql_batch_write(domain, steps):
    """Run several named writes as one atomic transaction — `steps` is
    (query_name, params) tuples, all from `domain`. Either every step
    commits together, or a failure rolls back everything already run.
    Used for writes spanning more than one table. Returns each step's
    rowcount, in order."""
    queries = load_queries(domain)
    conn = _connect()
    try:
        cur = conn.cursor()
        rowcounts = []
        for name, params in steps:
            cur.execute(queries[name], params)
            rowcounts.append(cur.rowcount)
        conn.commit()
        return rowcounts
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
