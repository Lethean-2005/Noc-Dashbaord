"""Tests for init_cache_db()'s schema-mismatch detection — specifically the
case where only the PRIMARY KEY changed (e.g. incident_by_status going from
`incident_id TEXT PRIMARY KEY` to `PRIMARY KEY (incident_id, site_code)`,
once a multi-site incident needed more than one row per incident_id). The
column-name-only comparison this used to rely on can't see that kind of
change — same column names, different key — so it never dropped/recreated
the table, and the app kept crashing with "UNIQUE constraint failed:
incident_by_status.incident_id" against a stale table left over from before
the fix, even after the code was updated and the process restarted.
"""

from app.database.cache import _expected_pk_columns, get_cache_conn, init_cache_db
from app.repositories.incident.incident_status_cache_repository import IncidentStatusCacheRepository


def test_expected_pk_columns_parses_composite_primary_key():
    schema = "CREATE TABLE IF NOT EXISTS {table} (a TEXT, b TEXT, PRIMARY KEY (a, b))"
    assert _expected_pk_columns(schema) == {"a", "b"}


def test_expected_pk_columns_parses_inline_primary_key():
    schema = "CREATE TABLE IF NOT EXISTS {table} (a TEXT PRIMARY KEY, b TEXT)"
    assert _expected_pk_columns(schema) == {"a"}


def test_init_cache_db_recreates_table_when_only_primary_key_changed(app):
    with app.app_context():
        conn = get_cache_conn()
        conn.execute("DROP TABLE incident_by_status")
        conn.execute(
            "CREATE TABLE incident_by_status ("
            "incident_id TEXT PRIMARY KEY, incident_numeric_id INTEGER, incident_status TEXT, wo_id TEXT, "
            "wo_numeric_id INTEGER, wo_created_at TEXT, wo_status TEXT, resolved_at TEXT, site_name TEXT, "
            "site_code TEXT, occurred_at TEXT, overdue TEXT, category TEXT, "
            "l1_noc_investigation_result TEXT, nms TEXT, hub_site TEXT, site_grade TEXT, "
            "province TEXT, district TEXT, commune TEXT)"
        )
        conn.commit()
        conn.close()

        init_cache_db()

        conn = get_cache_conn()
        try:
            info = conn.execute("PRAGMA table_info(incident_by_status)").fetchall()
            pk_columns = {row["name"] for row in info if row["pk"]}
            assert pk_columns == {"incident_id", "site_code"}

            # Same incident, two different sites — used to raise "UNIQUE
            # constraint failed: incident_by_status.incident_id" before the
            # PRIMARY KEY became composite.
            conn.execute(
                "INSERT INTO incident_by_status (incident_id, site_code) VALUES ('INC-1', '7210')"
            )
            conn.execute(
                "INSERT INTO incident_by_status (incident_id, site_code) VALUES ('INC-1', '7032')"
            )
            conn.commit()
            count = conn.execute("SELECT COUNT(*) FROM incident_by_status").fetchone()[0]
            assert count == 2
        finally:
            conn.close()


def test_incident_status_cache_repository_writes_multi_site_incident_rows(app):
    """End-to-end through the real repository (replace_all/fetch_all), not
    raw SQL — the exact write path incident_sync_service.py uses every
    sync cycle, reproducing the original "Incident-by-status cache write
    failed: UNIQUE constraint failed: incident_by_status.incident_id"
    error against two rows for the same multi-site incident."""
    with app.app_context():
        repo = IncidentStatusCacheRepository()
        rows = [
            {"incident_id": "INC-1", "site_code": "7210", "site_name": "Site A"},
            {"incident_id": "INC-1", "site_code": "7032", "site_name": "Site B"},
        ]
        full_rows = [
            {col: row.get(col) for col in IncidentStatusCacheRepository.columns} for row in rows
        ]

        repo.replace_all("incident_by_status", full_rows)

        fetched = repo.fetch_all("incident_by_status")
        assert len(fetched) == 2
        assert {r["site_code"] for r in fetched} == {"7210", "7032"}
