def test_reports_index_returns_200(client):
    response = client.get("/reports/")
    assert response.status_code == 200
