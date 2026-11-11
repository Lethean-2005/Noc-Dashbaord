"""Execute production timestamp selection and active-alert filters on test records."""
import sqlite3

import pytest

from app.database.sql_loader import load_queries

START = "2026-11-10 01:00:00"
CREATED = "2026-11-10 01:05:00"
CLEAR = "2026-11-10 02:00:00"
RESOLVED = "2026-11-10 03:00:00"
CLOSED = "2026-11-10 04:00:00"


def database(source, status, cleared, resolved, closed, issue=START, created=CREATED, flag=False):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""CREATE TABLE object_322 (
        incident_id TEXT, source TEXT, status TEXT, incident_category TEXT,
        issue_occurred_at TEXT, created_at TEXT, resolved_at TEXT, closed_at TEXT,
        cleared_alarm_received_at TEXT, cleared_alarm_received INTEGER,
        actual_root_cause TEXT, resolution TEXT);""")
    conn.execute("INSERT INTO object_322 VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
        "INC-TEST", source, status, "site_down", issue, created, resolved, closed,
        cleared, flag, "Actual cause", "Actual recovery",
    ))
    return conn


def restored(conn):
    query = load_queries("incident_site_down_restored_by_ids")["incident_site_down_restored_by_ids"]
    # SQLite lacks PostgreSQL array binding; keep production CASE/WHERE intact.
    query = query.replace("= ANY(:incident_ids)", "IN ('INC-TEST')")
    return [dict(row) for row in conn.execute(query)]


@pytest.mark.parametrize("status", ["new", "in_progress", "resolved", "closed", "reopened"])
def test_alarms_use_clear_received_at_instead_of_resolved_or_closed(status):
    conn = database(" AlArMs ", status, CLEAR, RESOLVED, CLOSED)
    try:
        rows = restored(conn)
    finally:
        conn.close()
    assert len(rows) == 1
    assert rows[0]["Occurred At"] == START
    assert rows[0]["Restored At"] == CLEAR
    assert rows[0]["Actual Root Cause"] == "Actual cause"
    assert rows[0]["Resolution"] == "Actual recovery"


@pytest.mark.parametrize("cleared,resolved,issue,eligible", [
    (CLEAR, None, START, True),
    (None, RESOLVED, START, False),
    (None, None, START, False),
    ("2026-11-10 00:59:59", RESOLVED, START, False),
    (START, None, START, True),
    (CLEAR, RESOLVED, None, False),
])
def test_alarm_clear_time_is_required_and_must_not_precede_start(cleared, resolved, issue, eligible):
    conn = database("alarms", "closed", cleared, resolved, CLOSED, issue=issue)
    try:
        assert bool(restored(conn)) is eligible
    finally:
        conn.close()


@pytest.mark.parametrize("source", ["noc", "manually", "field", "customer complaint"])
@pytest.mark.parametrize("resolved", [RESOLVED, None])
def test_non_alarm_sources_still_use_created_at_and_closed_at(source, resolved):
    conn = database(source, "resolved", CLEAR, resolved, CLOSED)
    try:
        rows = restored(conn)
    finally:
        conn.close()
    assert rows[0]["Occurred At"] == CREATED
    assert rows[0]["Restored At"] == CLOSED


@pytest.mark.parametrize("source", ["noc", "manually"])
def test_non_alarm_sources_wait_for_close_even_when_clear_and_resolved_are_filled(source):
    conn = database(source, "resolved", CLEAR, RESOLVED, None)
    try:
        assert restored(conn) == []
    finally:
        conn.close()


@pytest.mark.parametrize("source", [None, "", "   "])
def test_missing_source_does_not_guess_a_restoration_time(source):
    conn = database(source, "closed", CLEAR, RESOLVED, CLOSED)
    try:
        assert restored(conn) == []
    finally:
        conn.close()


@pytest.mark.parametrize("source,cleared,resolved,closed,flag,active", [
    ("alarms", None, RESOLVED, None, False, True),
    ("alarms", CLEAR, None, None, False, False),
    ("alarms", None, None, None, True, False),
    (" AlArMs ", None, None, None, False, True),
    ("noc", CLEAR, RESOLVED, None, False, True),
    ("noc", None, None, CLOSED, False, False),
    ("manually", CLEAR, RESOLVED, None, False, True),
])
def test_active_alert_filter_matches_the_source_specific_restoration_rule(source, cleared, resolved, closed, flag, active):
    conn = database(source, "in_progress", cleared, resolved, closed, flag=flag)
    query = load_queries("incident_site_down")["incident_site_down"]
    # Run the complete production WHERE clause; site-name joins are irrelevant here.
    where = "inc.incident_category" + query.split("WHERE inc.incident_category", 1)[1].split("ORDER BY", 1)[0]
    try:
        rows = conn.execute("SELECT inc.incident_id FROM object_322 inc WHERE " + where).fetchall()
        assert bool(rows) is active
    finally:
        conn.close()
