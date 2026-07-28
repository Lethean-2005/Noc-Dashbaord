"""Tests for IncidentSyncService's row normalization — specifically the
NMS raw-code translation (moved this session from a per-query SQL CASE
block to one shared Python constant) and the last_comments field added to
incident_site_down so the Telegram alert can read it from the same cache
instead of running its own separate Postgres query.
"""
from app.services.incident.incident_sync_service import IncidentSyncService


def _site_down_source_row(**overrides):
    row = {
        "Incident ID": "INC1", "Incident Numeric ID": 1, "Incident Status": "New",
        "INC-WO ID": "WO1", "INC-WO Numeric ID": 1, "INC-WO Created At": None,
        "INC-WO Status": "New", "Site Name": "Site A", "Site Code": "S1",
        "Occurred At": None, "L1 NOC Investigation Result": "",
        "Last Comments": "on-site now", "NMS Code": 7,
        "Hub Site": "", "Site Grade": "", "Province": "", "District": "", "Commune": "",
    }
    row.update(overrides)
    return row


def test_normalize_incident_site_down_row_translates_known_nms_code():
    row = _site_down_source_row(**{"NMS Code": 7})
    normalized = IncidentSyncService._normalize_incident_site_down_row(row)
    assert normalized["nms"] == "Nokia"


def test_normalize_incident_site_down_row_blanks_unknown_nms_code():
    row = _site_down_source_row(**{"NMS Code": 999})
    normalized = IncidentSyncService._normalize_incident_site_down_row(row)
    assert normalized["nms"] == ""


def test_normalize_incident_site_down_row_carries_last_comments():
    row = _site_down_source_row(**{"Last Comments": "waiting for parts"})
    normalized = IncidentSyncService._normalize_incident_site_down_row(row)
    assert normalized["last_comments"] == "waiting for parts"


def test_normalize_incident_site_down_row_defaults_blank_last_comments_to_empty_string():
    row = _site_down_source_row(**{"Last Comments": None})
    normalized = IncidentSyncService._normalize_incident_site_down_row(row)
    assert normalized["last_comments"] == ""
