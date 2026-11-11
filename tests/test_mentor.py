def test_mentor_index_returns_200(client):
    response = client.get("/mentor/")
    assert response.status_code == 200


def test_mentor_template_has_only_site_code_and_is_not_cached(client):
    response = client.get('/mentor/template')
    assert response.status_code == 200
    assert response.get_data(as_text=True) == 'site_code\n'
    assert response.headers['Cache-Control'] == 'no-store'


def test_mentor_page_has_compact_monitoring_badges_and_alphanumeric_input(client):
    response = client.get('/mentor/')
    html = response.get_data(as_text=True)
    assert html.count('class="mentor-monitor-badge"') == 8
    assert 'inputmode="text"' in html
    assert 'Site codes accept letters and numbers.' in html
