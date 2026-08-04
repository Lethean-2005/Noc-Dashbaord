"""Tests for IncidentSyncService's row normalization — the NMS raw-code
translation (resolved via the local ne_nms_lookup_cache, site_code -> raw
code, instead of being joined inside each query's own SQL), the
last_comments field on incident_site_down so the Telegram alert can read it
from the same cache instead of running its own separate Postgres query,
and the "latest INC-WO per (incident, site)" batching (resolved via one
batched fetch scoped to a batch of incident ids, instead of a per-row
LATERAL subquery against the foreign object_324 table — see
_latest_wo_by_incident_site()'s docstring for why that mattered).
"""
from app.services.incident.incident_sync_service import IncidentSyncService


def _site_down_source_row(**overrides):
    row = {
        "Incident ID": "INC1", "Incident Numeric ID": 1, "Incident Status": "New",
        "Site Name": "Site A", "Site Numeric ID": 10, "Site Code": "S1",
        "Occurred At": None, "L1 NOC Investigation Result": "",
        "Last Comments": "on-site now",
        "Hub Site": "", "Site Grade": "", "Province": "", "District": "", "Commune": "",
    }
    row.update(overrides)
    return row


def _wo_row(**overrides):
    row = {
        "Incident Numeric ID": 1, "Site Numeric ID": 10,
        "INC-WO ID": "WO1", "INC-WO Numeric ID": 1, "INC-WO Created At": None,
        "INC-WO Status": "New", "Resolved At": None,
    }
    row.update(overrides)
    return row


def test_normalize_incident_site_down_row_translates_known_nms_code():
    row = _site_down_source_row()
    normalized = IncidentSyncService._normalize_incident_site_down_row(row, {"S1": 7}, {})
    assert normalized["nms"] == "Nokia"


def test_normalize_incident_site_down_row_blanks_unknown_nms_code():
    row = _site_down_source_row()
    normalized = IncidentSyncService._normalize_incident_site_down_row(row, {"S1": 999}, {})
    assert normalized["nms"] == ""


def test_normalize_incident_site_down_row_blanks_nms_code_when_site_has_no_ne():
    row = _site_down_source_row()
    normalized = IncidentSyncService._normalize_incident_site_down_row(row, {}, {})
    assert normalized["nms"] == ""


def test_normalize_incident_site_down_row_carries_last_comments():
    row = _site_down_source_row(**{"Last Comments": "waiting for parts"})
    normalized = IncidentSyncService._normalize_incident_site_down_row(row, {}, {})
    assert normalized["last_comments"] == "waiting for parts"


def test_normalize_incident_site_down_row_defaults_blank_last_comments_to_empty_string():
    row = _site_down_source_row(**{"Last Comments": None})
    normalized = IncidentSyncService._normalize_incident_site_down_row(row, {}, {})
    assert normalized["last_comments"] == ""


def test_normalize_incident_site_down_row_fills_wo_fields_from_wo_by_key():
    row = _site_down_source_row()
    wo_by_key = {(1, 10): _wo_row(**{"INC-WO ID": "WO42", "INC-WO Status": "New"})}
    normalized = IncidentSyncService._normalize_incident_site_down_row(row, {}, wo_by_key)
    assert normalized["wo_id"] == "WO42"
    assert normalized["wo_status"] == "New"


def test_normalize_incident_site_down_row_blanks_wo_fields_when_site_has_no_wo():
    row = _site_down_source_row()
    normalized = IncidentSyncService._normalize_incident_site_down_row(row, {}, {})
    assert normalized["wo_id"] == ""
    assert normalized["wo_numeric_id"] is None
    assert normalized["wo_status"] == ""


def test_normalize_status_row_fills_wo_fields_from_wo_by_key():
    row = _site_down_source_row()
    wo_by_key = {(1, 10): _wo_row(**{"INC-WO ID": "WO42", "Resolved At": None})}
    normalized = IncidentSyncService._normalize_status_row(row, {}, wo_by_key)
    assert normalized["wo_id"] == "WO42"


def test_normalize_status_row_does_not_cross_match_a_different_sites_wo():
    """A site with no INC-WO of its own must stay blank, not silently show
    another site's — this was a real bug the old LATERAL join once had
    (fixed by requiring wo.site = sites.id); the batched replacement must
    not reintroduce it."""
    row = _site_down_source_row(**{"Site Numeric ID": 99})
    wo_by_key = {(1, 10): _wo_row()}
    normalized = IncidentSyncService._normalize_status_row(row, {}, wo_by_key)
    assert normalized["wo_id"] == ""


def test_nms_by_site_reads_local_cache_keyed_by_site_code():
    class FakeNeNmsLookupCacheRepo:
        def fetch_all(self, table):
            assert table == "ne_nms_lookup_cache"
            return [{"site_code": "S1", "nms_code": "7"}, {"site_code": "S2", "nms_code": "3"}]

    svc = IncidentSyncService(ne_nms_lookup_cache_repository=FakeNeNmsLookupCacheRepo())

    assert svc._nms_by_site() == {"S1": "7", "S2": "3"}


class FakeIncidentRepoForWo:
    def __init__(self, wo_rows):
        self._wo_rows = wo_rows
        self.requested_ids = None

    def fetch_wo_by_incident_ids(self, incident_ids):
        self.requested_ids = incident_ids
        return self._wo_rows


def test_latest_wo_by_incident_site_requests_only_this_batchs_incident_ids():
    repo = FakeIncidentRepoForWo([])
    svc = IncidentSyncService(incident_repository=repo)
    rows = [_site_down_source_row(**{"Incident Numeric ID": 1}), _site_down_source_row(**{"Incident Numeric ID": 2})]

    svc._latest_wo_by_incident_site(rows)

    assert repo.requested_ids == [1, 2]


def test_latest_wo_by_incident_site_picks_newest_created_at():
    older = _wo_row(**{"INC-WO ID": "WO-OLD", "INC-WO Created At": "2026-01-01"})
    newer = _wo_row(**{"INC-WO ID": "WO-NEW", "INC-WO Created At": "2026-06-01"})
    repo = FakeIncidentRepoForWo([older, newer])
    svc = IncidentSyncService(incident_repository=repo)

    result = svc._latest_wo_by_incident_site([_site_down_source_row()])

    assert result[(1, 10)]["INC-WO ID"] == "WO-NEW"


def test_latest_wo_by_incident_site_prefers_a_real_timestamp_over_none():
    """Matches the old SQL's ORDER BY created_at DESC NULLS LAST — a WO
    with no created_at never beats one that has a real timestamp,
    regardless of fetch order."""
    no_timestamp = _wo_row(**{"INC-WO ID": "WO-NULL", "INC-WO Created At": None})
    has_timestamp = _wo_row(**{"INC-WO ID": "WO-DATED", "INC-WO Created At": "2026-01-01"})
    repo = FakeIncidentRepoForWo([no_timestamp, has_timestamp])
    svc = IncidentSyncService(incident_repository=repo)

    result = svc._latest_wo_by_incident_site([_site_down_source_row()])

    assert result[(1, 10)]["INC-WO ID"] == "WO-DATED"


def test_latest_wo_by_incident_site_keeps_wos_separate_per_site():
    site_a_wo = _wo_row(**{"Site Numeric ID": 10, "INC-WO ID": "WO-A"})
    site_b_wo = _wo_row(**{"Site Numeric ID": 20, "INC-WO ID": "WO-B"})
    repo = FakeIncidentRepoForWo([site_a_wo, site_b_wo])
    svc = IncidentSyncService(incident_repository=repo)
    rows = [_site_down_source_row(**{"Site Numeric ID": 10}), _site_down_source_row(**{"Site Numeric ID": 20})]

    result = svc._latest_wo_by_incident_site(rows)

    assert result[(1, 10)]["INC-WO ID"] == "WO-A"
    assert result[(1, 20)]["INC-WO ID"] == "WO-B"


def test_latest_wo_by_incident_site_never_matches_a_siteless_wo_to_a_siteless_row():
    """Real bug found live (INC-0000122533/INC-0000118176): the old SQL
    matched via `wo.site = sites.id`, and SQL's NULL = NULL is never true,
    so a WO with no site could never match an incident row with no site
    either — it always stayed correctly blank. A naive Python dict keyed
    by (incident_id, site_id) would wrongly match here instead, since
    None == None IS true in Python. Both the incident's row and its WO
    genuinely have no site in this scenario (confirmed live), and the
    result must still come back empty, not the WO."""
    siteless_wo = _wo_row(**{"Site Numeric ID": None, "INC-WO ID": "WO-SHOULD-NOT-MATCH"})
    repo = FakeIncidentRepoForWo([siteless_wo])
    svc = IncidentSyncService(incident_repository=repo)
    rows = [_site_down_source_row(**{"Site Numeric ID": None})]

    result = svc._latest_wo_by_incident_site(rows)

    assert (1, None) not in result
