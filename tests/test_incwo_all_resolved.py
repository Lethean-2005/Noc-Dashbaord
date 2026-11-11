"""Exercise the actual summary SQL against representative sibling-WO cases."""
import sqlite3

from app.database.sql_loader import load_queries
from app.database.cache import get_cache_conn
from app.services.incwo.incwo_service import IncWoService


def test_source_flag_and_every_sibling_must_be_resolved():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.create_function("INITCAP", 1, lambda value: value.title() if value else value)
    c.executescript("""
      CREATE TABLE object_322 (id INTEGER, incident_id TEXT, status TEXT, incident_category TEXT,
                              site_code TEXT, issue_occurred_at TEXT, all_wo_is_resolved BOOLEAN, site_text TEXT);
      CREATE TABLE object_324 (id INTEGER, parent_incident INTEGER, status TEXT, resolved_at TEXT);
    """)
    for i in range(1, 8):
        c.execute("INSERT INTO object_322 (id,incident_id,status,incident_category,site_code,issue_occurred_at,all_wo_is_resolved) VALUES (?,?,?,?,?,?,?)", (i, f"INC{i}", "closed" if i == 7 else "in_progress", "site_down", "0460", "2026-11-06", i != 6))
    states = {1: ["resolved"] * 3, 2: ["resolved", "in_progress", "new"], 3: ["resolved", "closed"],
              4: ["resolved", None], 5: [], 6: ["resolved"], 7: ["resolved"]}
    n = 0
    for parent, statuses in states.items():
        for status in statuses:
            n += 1
            c.execute("INSERT INTO object_324 VALUES (?,?,?,?)", (n, parent, status, "2026-11-06 02:00:00"))
    rows = [dict(r) for r in c.execute(load_queries("inc_wo_all_resolved")["inc_wo_all_resolved"])]
    c.close()
    assert [r["incident_id"] for r in rows] == ["INC1"]
    assert rows[0]["wo_count"] == rows[0]["resolved_wo_count"] == 3


def test_badge_drilldown_and_export_count_incidents_not_wos(client, app):
    with app.app_context():
        c = get_cache_conn()
        c.execute("INSERT INTO inc_wo_all_resolved (incident_numeric_id,incident_id,incident_status,incident_category,site_code,wo_count,resolved_wo_count,all_wo_is_resolved) VALUES (1,'INC1','In Progress','Site Down','0460',3,3,1)")
        c.commit()
        c.close()
        assert IncWoService().get_all_resolved_count() == 1
    response = client.get('/drilldown?scope=INC-WO+All+Resolved&type=all_resolved')
    assert response.status_code == 200
    assert 'INC1' in response.get_data(as_text=True)
    assert '1 incidents' in response.get_data(as_text=True)
    assert 'Worklog' not in response.get_data(as_text=True)
    html = client.get('/').get_data(as_text=True)
    assert html.index('Overdue Site-Down') < html.index('All WO is Resolved') < html.index('data-badge-key="incwo_new"')
    exported = client.get('/drilldown/download?scope=INC-WO+All+Resolved&type=all_resolved')
    assert exported.status_code == 200
    assert 'INC1' in exported.get_data(as_text=True)


def test_incident_site_codes_preserve_all_sites_and_leading_zeroes():
    from app.utils.incident_site_codes import incident_site_codes
    assert incident_site_codes({"site_text": "KR0411,KR0047", "site_code": None}, {"0411", "0047"}) == "0411/0047"
    assert incident_site_codes({"site_text": "KR0411,KR0047,KR0411", "site_code": "0411"}, {"0411", "0047"}) == "0411/0047"
    assert incident_site_codes({"site_code": "A0143"}, {"A0143"}) == "A0143"
    assert incident_site_codes({"site_text": "AB1234"}, {"AB1234", "1234"}) == "AB1234"
    assert incident_site_codes({"site_text": "XX9999"}, set()) == "XX9999"
    assert incident_site_codes({}, set()) == ""
