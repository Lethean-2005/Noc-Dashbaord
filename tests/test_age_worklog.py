"""Age worklog popups include incidents even when no worklog is cached."""
from pathlib import Path

import pytest

from app.services.incident.incident_service import IncidentService


class RowsRepository:
    def __init__(self, rows):
        self.rows = rows
        self.reads = 0

    def fetch_all(self, table):
        self.reads += 1
        return self.rows


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setattr('app.services.incident.incident_service.elapsed_minutes', lambda value: 60)
    incidents = [dict(incident_id=f'INC-TEST-{i}', incident_numeric_id=i,
                      category='Site Down', incident_status='In Progress',
                      occurred_at='2026-01-01 00:00:00', site_code=f'TEST-{i}')
                 for i in range(1, 10)]
    logs = [dict(incident_numeric_id=i, incident_id=f'INC-TEST-{i}',
                 created_at='2026-01-01 00:30:00', created_by='Operator', entry_text='Checking service')
            for i in range(1, 5)]
    return IncidentService(status_cache_repository=RowsRepository(incidents),
                           worklog_cache_repository=RowsRepository(logs))


def test_nine_incidents_with_four_worklogs_all_appear(service):
    result = service.get_worklog_by_age_bucket('age_lt4')['age_lt4']
    assert len(result) == service.get_incident_age_buckets()['<4h'] == 9
    assert len([incident for incident in result if incident['entries']]) == 4
    assert len([incident for incident in result if not incident['entries']]) == 5
    assert {incident['incident_id'] for incident in result} == {f'INC-TEST-{i}' for i in range(1, 10)}


def test_multi_site_incident_appears_once_and_logs_remain_newest_first(service):
    service.status_cache_repository.rows.append(dict(service.status_cache_repository.rows[0], site_code='SECOND-SITE'))
    service.worklog_cache_repository.rows.append(dict(service.worklog_cache_repository.rows[0],
                                                     created_at='2026-01-01 00:45:00', entry_text='Latest update'))
    result = service.get_worklog_by_age_bucket('age_lt4')['age_lt4']
    assert len(result) == 9
    assert result[0]['incident_id'] == 'INC-TEST-1'
    assert [entry['entry_text'] for entry in result[0]['entries']] == ['Latest update', 'Checking service']


def test_populated_bucket_has_button_without_reading_worklogs(service):
    service.worklog_cache_repository.rows.clear()
    availability = service.get_worklog_age_availability()
    assert availability['age_lt4'] is True
    assert availability['age_4_8'] is False
    assert service.worklog_cache_repository.reads == 0
    assert len(service.get_worklog_by_age_bucket('age_lt4')['age_lt4']) == 9


def test_fragment_displays_all_incidents_and_explicit_missing_worklog(client, monkeypatch, service):
    monkeypatch.setattr('app.routes.dashboard.incident_service', service)
    response = client.get('/dashboard/worklog/age_lt4')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert html.count('class="volume-category-row"') == 9
    assert html.count('No worklog available for this incident.') == 5
    assert html.count('Checking service') == 4


def test_graph_popup_available_when_every_incident_has_no_worklog(client, monkeypatch, service):
    service.worklog_cache_repository.rows.clear()
    monkeypatch.setattr('app.routes.dashboard.incident_service', service)
    html = client.get('/graph-cards').get_data(as_text=True)
    assert 'data-age-worklog-modal="incidentAgeWorklogModal_age_lt4"' in html
    assert 'id="incidentAgeWorklogModal_age_lt4"' in html
    assert service.worklog_cache_repository.reads == 0


def test_expanding_incident_shows_its_empty_message_or_real_entries(app):
    playwright = pytest.importorskip('playwright.sync_api')
    from flask import render_template

    with app.app_context():
        html = render_template('dashboard/partials/age_worklog_table.html', incidents=[
            {'incident_id': 'INC-EMPTY', 'entries': []},
            {'incident_id': 'INC-LOG', 'entries': [{'created_at': '2026-01-01', 'created_by': 'Operator', 'entry_text': 'Service restored'}]},
        ])
    with playwright.sync_playwright() as engine:
        try:
            browser = engine.chromium.launch(channel='msedge', headless=True)
        except playwright.Error:
            pytest.skip('Microsoft Edge is unavailable')
        page = browser.new_page()
        try:
            page.set_content('<style>.volume-duration-panel{display:none}.volume-duration-panel.is-visible{display:table-row-group}</style><div class="modal">' + html + '</div>')
            page.add_script_tag(path=str(Path('app/static/js/graph_cards.js').resolve()))
            message = page.get_by_text('No worklog available for this incident.')
            playwright.expect(message).not_to_be_visible()
            page.get_by_text('INC-EMPTY', exact=True).click()
            playwright.expect(message).to_be_visible()
            page.get_by_text('INC-LOG', exact=True).click()
            playwright.expect(page.get_by_text('Service restored')).to_be_visible()
            playwright.expect(message).not_to_be_visible()
        finally:
            browser.close()
