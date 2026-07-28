def test_index_returns_200(client):
    response = client.get("/")
    assert response.status_code == 200


def test_drilldown_returns_200(client):
    response = client.get("/drilldown?title=VVIP+Door+Alarm&label=Door+Alarm&value=0&scope=VVIP+Site")
    assert response.status_code == 200
    assert b"No VIP/VVIP site alarms found" in response.data
