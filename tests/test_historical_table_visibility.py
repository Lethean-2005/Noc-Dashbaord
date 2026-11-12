"""Historical tables must show every matching row without pagination."""
import csv
import io
from urllib.parse import urlencode

from lxml import html
import pytest

from app.routes import dashboard

SCOPES = {
    "SLA Compliance": "sla_compliance_details",
    "Response Time Duration": "response_time_duration",
    "Resolution Time Duration": "resolution_time_duration",
}


@pytest.mark.parametrize("scope,template", SCOPES.items())
def test_all_matching_records_are_visible_and_exported(client, monkeypatch, scope, template):
    rows = [{"incident_id": f"TEST-{index:05d}", "category": "Power", "iso_week": "2026-W45"}
            for index in range(1000)]
    monkeypatch.setitem(dashboard._SCOPE_HANDLERS, scope, {
        "fetch": lambda badge: rows,
        "template": "drilldown/" + template + ".html",
        "csv_columns": [("incident_id", "Incident ID")],
    })
    query = urlencode({"scope": scope, "page": 2})
    response = client.get("/drilldown?" + query)
    assert response.status_code == 200
    document = html.fromstring(response.data)
    displayed = document.xpath('//div[contains(@class,"drilldown-table-wrap")]//tbody/tr/td[1]//text()')
    assert [value.strip() for value in displayed if value.strip()] == [row["incident_id"] for row in rows]
    assert b'table-pagination' not in response.data
    assert b'1000 records' in response.data
    exported = client.get("/drilldown/download?" + query)
    assert len(list(csv.reader(io.StringIO(exported.get_data(as_text=True))))) == 1001
