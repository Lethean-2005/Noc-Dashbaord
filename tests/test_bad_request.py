"""Bad requests retain protection and offer readable recovery."""
import pytest


def test_missing_csrf_session_has_styled_recovery(app, client):
    app.config["WTF_CSRF_ENABLED"] = True
    response = client.post('/mentor/add', data={'csrf_token': 'stale-token', 'site_codes': 'TEST'})
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert 'nf3-card' in html and '400 Bad Request' in html
    assert 'Return to Mentor Site' in html
    assert 'This request was not processed.' in html
    assert response.headers['Cache-Control'] == 'no-store'


@pytest.mark.parametrize('path', ['/mentor/validate', '/api/v1/mentor/validate', '/mentor/upload'])
def test_csrf_json_error_can_be_displayed(app, client, path):
    app.config['WTF_CSRF_ENABLED'] = True
    response = client.post(path, headers={'Accept': 'application/json'})
    assert response.status_code == 400
    assert 'Open the page again' in response.json['error']


def test_mentor_placeholder_has_no_example(client):
    html = client.get('/mentor/').get_data(as_text=True)
    assert 'placeholder="Enter site codes"' in html
    assert 'placeholder="e.g.' not in html


def test_method_not_allowed_matches_error_style_and_preserves_allow(client):
    response = client.get('/mentor/add')
    assert response.status_code == 405
    assert 'POST' in response.headers['Allow']
    html = response.get_data(as_text=True)
    assert 'nf3-card' in html and '405 Method Not Allowed' in html
    assert 'Return to Mentor Site' in html
    assert response.headers['Cache-Control'] == 'no-store'


def test_api_method_not_allowed_returns_json_and_allow(client):
    response = client.get('/api/v1/mentor/validate')
    assert response.status_code == 405
    assert 'POST' in response.headers['Allow']
    assert 'request method' in response.json['error']
