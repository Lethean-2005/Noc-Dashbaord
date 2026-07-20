def test_index_returns_200(client):
    response = client.get("/")
    assert response.status_code == 200


def test_overview_returns_200(client):
    response = client.get("/overview")
    assert response.status_code == 200


def test_drilldown_returns_200(client):
    response = client.get("/drilldown?title=VVIP+Door+Alarm&label=Door+Alarm&value=0&scope=VVIP+Site")
    assert response.status_code == 200
    assert b"No alarms found for VVIP Site" in response.data
