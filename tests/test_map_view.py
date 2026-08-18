"""Smoke test for the Map View route — full end-to-end render against an
empty local cache (see tests/conftest.py), same shape as
tests/test_dashboard.py's own route smoke tests.
"""


def test_map_view_returns_200(client):
    response = client.get("/map/")
    assert response.status_code == 200


def test_map_view_renders_zero_sites_with_empty_cache(client):
    response = client.get("/map/")
    assert b"0 sites plotted" in response.data
