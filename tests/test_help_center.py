"""Help links, retained documentation, and configured refresh descriptions."""
import pytest
from app.help_guides import CARD_GUIDES
from app.routes.help import HELP_ARTICLES, DOWNLOADABLE_DOCS


@pytest.mark.parametrize("slug", list(CARD_GUIDES))
def test_card_guides_open_from_directory(client, slug):
    landing = client.get("/help").get_data(as_text=True)
    assert f'/help/articles/{slug}' in landing
    response = client.get(f"/help/articles/{slug}")
    assert response.status_code == 200
    assert "When the data refreshes" in response.get_data(as_text=True)


@pytest.mark.parametrize("slug", list(HELP_ARTICLES))
def test_original_articles_remain_available(client, slug):
    assert client.get(f"/help/articles/{slug}").status_code == 200


@pytest.mark.parametrize("filename", list(DOWNLOADABLE_DOCS))
def test_original_pdf_links_remain_available(client, filename):
    assert filename in client.get("/help").get_data(as_text=True)
    assert client.get(f"/help/downloads/{filename}").status_code == 200


def test_guide_shows_actual_configured_interval(app, client):
    app.config["VIP_ALARM_SYNC_INTERVAL_SECONDS"] = 420
    text = client.get("/help/articles/card-vip-vvip").get_data(as_text=True)
    assert "7 minutes" in text


def test_unknown_article_is_not_a_template_path(client):
    assert client.get("/help/articles/not-an-article").status_code == 404


@pytest.mark.parametrize("slug", list(CARD_GUIDES))
def test_card_guides_do_not_expose_code_file_paths(client, slug):
    html = client.get(f"/help/articles/{slug}").get_data(as_text=True)
    assert "app/database/queries/" not in html
    assert "app/services/" not in html
    assert ".sql" not in html
    assert "_SYNC_INTERVAL_SECONDS" not in html


@pytest.mark.parametrize("topic_id", ["getting-started", "live-alarms", "incidents", "trends", "tools", "data"])
def test_topic_directory_links_open(client, topic_id):
    assert f'/help/topics/{topic_id}' in client.get("/help").get_data(as_text=True)
    assert client.get(f"/help/topics/{topic_id}").status_code == 200


def test_unknown_topic_returns_not_found(client):
    assert client.get("/help/topics/not-a-topic").status_code == 404


from app.help_features import FEATURE_GUIDES
from app.help_reference import REFERENCE_GUIDES


@pytest.mark.parametrize("slug", list(FEATURE_GUIDES))
def test_feature_steps_and_demo_assets_are_available(client, slug):
    html = client.get(f"/help/articles/{slug}").get_data(as_text=True)
    assert "Step-by-step instructions" in html
    assert "What changes after saving" in html
    assert f"/help/articles/{slug}" in client.get("/help").get_data(as_text=True)
    for image, _caption in FEATURE_GUIDES[slug]["screenshots"]:
        assert f"images/{image}" in html
        response = client.get(f"/static/images/{image}")
        assert response.status_code == 200
        assert response.data.startswith(b"\x89PNG")


@pytest.mark.parametrize("slug", list(REFERENCE_GUIDES))
def test_pdf_reference_material_is_available_in_help(client, slug):
    html = client.get(f"/help/articles/{slug}").get_data(as_text=True)
    assert REFERENCE_GUIDES[slug]["entries"][0][0] in html
    assert f"/help/articles/{slug}" in client.get("/help").get_data(as_text=True)


def test_help_includes_pdf_worked_tables(client):
    html = client.get("/help/articles/card-sla").get_data(as_text=True)
    assert "Worked example: two overlapping lists" in html
    assert "Response failed only" in html
    assert "Resolution failed only" in html
    html = client.get("/help/articles/card-all-wo-resolved").get_data(as_text=True)
    assert "Worked example: check the flag and every WO" in html
