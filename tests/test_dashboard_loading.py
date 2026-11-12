"""Initial dashboard rendering must not build off-screen historical charts."""
from app.routes import dashboard


def test_initial_page_skips_expensive_historical_context(client, monkeypatch):
    def unexpected():
        raise AssertionError("Historical charts were computed on initial load")

    monkeypatch.setattr(dashboard, "_performance_cards_context", unexpected)
    response = client.get("/?response_time_category=Power&top_site_down_week=2026-11-02")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-lazy-url="/performance-cards"' in html
    assert 'name="response_time_category" value="Power"' in html
    assert 'name="top_site_down_week" value="2026-11-02"' in html
    assert 'id="perfTooltip"' not in html
    assert 'load_performance=1' in html


def test_full_page_fallback_and_chart_fragment_remain_available(client):
    full = client.get("/?load_performance=1")
    fragment = client.get("/performance-cards")
    assert full.status_code == fragment.status_code == 200
    assert b'id="perfTooltip"' in full.data
    assert b'id="perfTooltip"' in fragment.data
    assert b'data-lazy-url=' not in full.data


def test_lazy_loading_can_be_disabled_without_changing_routes(client, app):
    app.config["DASHBOARD_LAZY_PERFORMANCE"] = False
    response = client.get("/")
    assert response.status_code == 200
    assert b'id="perfTooltip"' in response.data
