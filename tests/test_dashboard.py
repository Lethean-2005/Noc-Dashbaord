def test_index_returns_200(client):
    response = client.get("/")
    assert response.status_code == 200


def test_drilldown_returns_200(client):
    response = client.get(
        "/drilldown?title=VVIP+Door+Alarm&label=Door+Alarm&value=0&scope=VVIP+Site"
    )
    assert response.status_code == 200
    assert b"No VIP/VVIP site alarms found" in response.data


def test_dc_low_high_drilldown_returns_200(client):
    response = client.get(
        "/drilldown?title=DC+Low%2FHigh&label=DC+Low%2FHigh&value=0&scope=DC+Low%2FHigh"
    )
    assert response.status_code == 200
    assert b"No DC Low/High found" in response.data


def test_incident_drilldown_returns_200(client):
    """Renders incidents.html — the "Incident" card's drilldown, backed by
    incident_by_status (now one row per (incident, site) pair, see
    tests/test_cache_migration.py). Empty here just proves the template
    still renders cleanly; the per-site fan-out itself is covered at the
    cache/repository level."""
    response = client.get("/drilldown?title=Incident&label=Incident&value=0&scope=Incident")
    assert response.status_code == 200
    assert b"No incidents found" in response.data


def _seed_inc_wo_rows(app, count):
    from app.repositories.incwo.incwo_status_cache_repository import IncWoStatusCacheRepository

    with app.app_context():
        rows = [
            {
                "incident_id": f"INC{i}",
                "incident_numeric_id": i,
                "incident_status": "New",
                "wo_id": f"WO{i}",
                "wo_numeric_id": i,
                "wo_created_at": f"2026-01-{(i % 28) + 1:02d} 00:00:00",
                "wo_status": "New",
                "resolved_at": "",
                "incident_category": "Site Down",
                "site_name": "Site A",
                "site_code": "S1",
                "overdue": "No",
                "support_level": "",
                "responsible_team": "",
                "fault_description": "",
                "nms": "",
                "hub_site": "",
                "site_grade": "",
                "province": "",
                "district": "",
                "commune": "",
            }
            for i in range(count)
        ]
        IncWoStatusCacheRepository().replace_all("inc_wo_by_status", rows)


def test_inc_wo_drilldown_caps_unfiltered_rows(client, app):
    """The plain "View INC-WO" link (no badge type) used to render every
    non-closed WO in one giant HTML table — at 2,400+ real rows this made
    the page feel stuck. Capped to the newest 500 for the HTML render
    only (see _SCOPE_HANDLERS["INC-WO"]["row_cap"])."""
    _seed_inc_wo_rows(app, 600)

    response = client.get("/drilldown?title=INC-WO&label=INC-WO&value=0&scope=INC-WO")

    assert response.status_code == 200
    assert response.data.count(b"<tr>") == 501  # 1 header row + 500 capped data rows
    assert b"Showing the newest 500 of 600 rows" in response.data


def test_inc_wo_drilldown_no_notice_when_under_cap(client, app):
    _seed_inc_wo_rows(app, 10)

    response = client.get("/drilldown?title=INC-WO&label=INC-WO&value=0&scope=INC-WO")

    assert response.status_code == 200
    assert response.data.count(b"<tr>") == 11  # 1 header row + 10 data rows
    assert b"Showing the newest" not in response.data


def test_inc_wo_csv_export_is_not_capped(client, app):
    """CSV export is a deliberate full data-dump use case, not a rendered
    HTML table a browser has to lay out — the row cap must not apply
    there, only to the HTML view."""
    _seed_inc_wo_rows(app, 600)

    response = client.get("/drilldown/download?scope=INC-WO&type=")

    assert response.status_code == 200
    # header row + 600 data rows, one CSV line each
    assert len(response.data.decode().strip().splitlines()) == 601


