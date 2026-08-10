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
