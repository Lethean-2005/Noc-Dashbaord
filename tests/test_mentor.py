def test_mentor_index_returns_200(client):
    response = client.get("/mentor/")
    assert response.status_code == 200
