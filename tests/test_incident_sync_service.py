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
        "Incident ID": "INC1",
        "Incident Numeric ID": 1,
        "Incident Status": "New",
        "Site Name": "Site A",
        "Site Numeric ID": 10,
        "Site Code": "S1",
        "Occurred At": None,
        "L1 NOC Investigation Result": "",
        "Last Comments": "on-site now",
        "Hub Site": "",
        "Site Grade": "",
        "Province": "",
        "District": "",
        "Commune": "",
    }
    row.update(overrides)
    return row


def _wo_row(**overrides):
    row = {
        "Incident Numeric ID": 1,
        "Site Numeric ID": 10,
        "INC-WO ID": "WO1",
        "INC-WO Numeric ID": 1,
        "INC-WO Created At": None,
        "INC-WO Status": "New",
        "Resolved At": None,
    }
    row.update(overrides)
    return row


def test_normalize_incident_site_down_row_carries_resolved_nms_name():
    # _nms_by_site() now resolves straight to a vendor NAME (onair VENDOR
    # column / confirmed actual_ran_vendor / NE-lookup, in that priority
    # order — see its own docstring) — the normalize function just reads
    # that dict, it doesn't translate a raw code itself anymore.
    row = _site_down_source_row()
    normalized = IncidentSyncService._normalize_incident_site_down_row(row, {"S1": "Nokia"}, {})
    assert normalized["nms"] == "Nokia"


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


def test_normalize_incident_site_down_row_carries_actual_root_cause():
    row = _site_down_source_row(**{"Actual Root Cause": "EDC grid outage"})
    normalized = IncidentSyncService._normalize_incident_site_down_row(row, {}, {})
    assert normalized["actual_root_cause"] == "EDC grid outage"


def test_normalize_incident_site_down_row_defaults_blank_actual_root_cause_to_empty_string():
    row = _site_down_source_row(**{"Actual Root Cause": None})
    normalized = IncidentSyncService._normalize_incident_site_down_row(row, {}, {})
    assert normalized["actual_root_cause"] == ""


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


def _incwo_source_row(**overrides):
    row = {
        "Incident ID": "INC1",
        "Incident Numeric ID": 1,
        "Incident Status": "New",
        "INC-WO ID": "WO1",
        "INC-WO Numeric ID": 1,
        "INC-WO Created At": None,
        "INC-WO Status": "New",
        "Resolved At": None,
        "Incident Category": "Site Down",
        "Site Name": "Site A",
        "Site Code": "S1",
        "overdue": "No",
        "Support Level": "",
        "Responsible Team": "",
        "Fault Description": "",
        "Hub Site": "",
        "Site Grade": "",
        "Province": "",
        "District": "",
        "Commune": "",
    }
    row.update(overrides)
    return row


def test_normalize_incwo_row_keeps_real_site_name():
    row = _incwo_source_row(**{"Site Name": "Real Site"})
    normalized = IncidentSyncService._normalize_incwo_row(row, {})
    assert normalized["site_name"] == "Real Site"


def test_normalize_incwo_row_falls_back_to_site_code_when_site_name_blank():
    """An "Other Site" WO (site not in the registered Site list) has no
    Site Name from the source at all — Site Code does get a COALESCE
    fallback to the parent Incident's own value (see inc_wo_by_status.sql),
    so label with that instead of leaving Site Name blank."""
    row = _incwo_source_row(**{"Site Name": "", "Site Code": "I0978"})
    normalized = IncidentSyncService._normalize_incwo_row(row, {})
    assert normalized["site_name"] == "Other Site (I0978)"


def test_normalize_incwo_row_falls_back_to_plain_other_site_when_site_code_also_blank():
    row = _incwo_source_row(**{"Site Name": "", "Site Code": ""})
    normalized = IncidentSyncService._normalize_incwo_row(row, {})
    assert normalized["site_name"] == "Other Site"


class FakeNeNmsLookupCacheRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self, table):
        assert table == "ne_nms_lookup_cache"
        return self._rows


class FakeSiteRanVendorCacheRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self, table):
        assert table == "site_ran_vendor_cache"
        return self._rows


def test_nms_by_site_reads_local_cache_keyed_by_site_code():
    ne_rows = [{"site_code": "S1", "nms_code": "7"}, {"site_code": "S2", "nms_code": "3"}]
    svc = IncidentSyncService(
        ne_nms_lookup_cache_repository=FakeNeNmsLookupCacheRepo(ne_rows),
        site_ran_vendor_cache_repository=FakeSiteRanVendorCacheRepo([]),
        mssql_site_onair_cache_repository=FakeMssqlSiteOnairCacheRepo([]),
    )

    result = svc._nms_by_site()
    assert result["S1"] == "Nokia"
    assert result["S2"] == "ZTE"


def test_nms_by_site_prefers_confirmed_actual_ran_vendor_code_over_ne_lookup():
    # S1's NE-based lookup says "7" (Nokia), but its confirmed
    # actual_ran_vendor code (20) says Huawei ("5") — the site-level
    # field wins since it's confirmed correct for this code (exact-count
    # match against Streamline's own "Actual RAN Vendor" filter, see
    # app/utils/nms.py).
    ne_rows = [{"site_code": "S1", "nms_code": "7"}]
    vendor_rows = [{"site_code": "S1", "actual_ran_vendor": 20}]
    svc = IncidentSyncService(
        ne_nms_lookup_cache_repository=FakeNeNmsLookupCacheRepo(ne_rows),
        site_ran_vendor_cache_repository=FakeSiteRanVendorCacheRepo(vendor_rows),
        mssql_site_onair_cache_repository=FakeMssqlSiteOnairCacheRepo([]),
    )

    assert svc._nms_by_site()["S1"] == "Huawei"


def test_nms_by_site_leaves_out_same_named_but_unconfirmed_huawei_codes():
    # 21 and 22 are ALSO Counterparty catalog records literally named
    # "Huawei" (see app/utils/nms.py) — but Streamline's own "Actual RAN
    # Vendor = Huawei" filter doesn't count either of them (only code 20
    # does), so this mapping deliberately doesn't either. A site linked to
    # 21/22 must fall through to the NE-based lookup, same as any other
    # unconfirmed code.
    ne_rows = [
        {"site_code": "S21", "nms_code": "5"},
        {"site_code": "S22", "nms_code": "3"},
    ]
    vendor_rows = [
        {"site_code": "S21", "actual_ran_vendor": 21},
        {"site_code": "S22", "actual_ran_vendor": 22},
    ]
    svc = IncidentSyncService(
        ne_nms_lookup_cache_repository=FakeNeNmsLookupCacheRepo(ne_rows),
        site_ran_vendor_cache_repository=FakeSiteRanVendorCacheRepo(vendor_rows),
        mssql_site_onair_cache_repository=FakeMssqlSiteOnairCacheRepo([]),
    )

    result = svc._nms_by_site()
    assert result["S21"] == "Huawei"
    assert result["S22"] == "ZTE"


def test_nms_by_site_ignores_unconfirmed_actual_ran_vendor_codes():
    # Code 58 is not in ACTUAL_RAN_VENDOR_TO_NMS_CODE (still unconfirmed —
    # see app/utils/nms.py) — the NE-based lookup must be left untouched.
    ne_rows = [{"site_code": "S1", "nms_code": "7"}]
    vendor_rows = [{"site_code": "S1", "actual_ran_vendor": 58}]
    svc = IncidentSyncService(
        ne_nms_lookup_cache_repository=FakeNeNmsLookupCacheRepo(ne_rows),
        site_ran_vendor_cache_repository=FakeSiteRanVendorCacheRepo(vendor_rows),
        mssql_site_onair_cache_repository=FakeMssqlSiteOnairCacheRepo([]),
    )

    assert svc._nms_by_site()["S1"] == "Nokia"


def test_nms_by_site_uses_confirmed_actual_ran_vendor_even_with_no_ne_row():
    ne_rows = []
    vendor_rows = [{"site_code": "S1", "actual_ran_vendor": 6}]
    svc = IncidentSyncService(
        ne_nms_lookup_cache_repository=FakeNeNmsLookupCacheRepo(ne_rows),
        site_ran_vendor_cache_repository=FakeSiteRanVendorCacheRepo(vendor_rows),
        mssql_site_onair_cache_repository=FakeMssqlSiteOnairCacheRepo([]),
    )

    assert svc._nms_by_site()["S1"] == "ZTE"


def test_nms_by_site_prefers_onair_vendor_column_over_confirmed_actual_ran_vendor():
    # The real bug this was fixed for: site 0511 had a confirmed
    # actual_ran_vendor code resolving to "Huawei", but the Map page (and
    # the real on-air equipment) says "ZTE" via mssql_site_onair's own
    # VENDOR column — that column is real NE inventory data and must win
    # over both other tiers whenever a site is on it.
    vendor_rows = [{"site_code": "S1", "actual_ran_vendor": 20}]  # confirmed -> Huawei
    onair_rows = [{"site_code": "S1", "vendor": "ZTE"}]
    svc = IncidentSyncService(
        ne_nms_lookup_cache_repository=FakeNeNmsLookupCacheRepo([]),
        site_ran_vendor_cache_repository=FakeSiteRanVendorCacheRepo(vendor_rows),
        mssql_site_onair_cache_repository=FakeMssqlSiteOnairCacheRepo(onair_rows),
    )

    assert svc._nms_by_site()["S1"] == "ZTE"


class FakeMssqlSiteOnairCacheRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self, table):
        assert table == "mssql_site_onair"
        return self._rows


def test_onair_vendor_by_site_code_reads_real_vendor_from_local_cache():
    rows = [
        {"site_code": "S1", "vendor": "Huawei"},
        {"site_code": "S2", "vendor": "ZTE"},
    ]
    svc = IncidentSyncService(mssql_site_onair_cache_repository=FakeMssqlSiteOnairCacheRepo(rows))

    result = svc._onair_vendor_by_site_code()
    assert result == {"S1": "Huawei", "S2": "ZTE"}


def test_onair_vendor_by_site_code_skips_rows_with_no_vendor():
    # mssql_site_onair_sync_service.py normalizes a missing VENDOR to ""
    # (never None) — confirmed on the real cache: 6 of 3,751 On-Air sites
    # have no vendor. Those must fall through to _resolve_vendor_name()'s
    # tier-2 actual_ran_vendor check, not resolve to a blank string.
    rows = [{"site_code": "S1", "vendor": ""}, {"site_code": "S2", "vendor": "Nokia"}]
    svc = IncidentSyncService(mssql_site_onair_cache_repository=FakeMssqlSiteOnairCacheRepo(rows))

    assert svc._onair_vendor_by_site_code() == {"S2": "Nokia"}


def test_resolve_vendor_name_prefers_onair_real_vendor_over_actual_ran_vendor_code():
    # S1's actual_ran_vendor code (20) would resolve to Huawei via the
    # confirmed-code tier, but mssql_site_onair's own real NE inventory
    # data says ZTE for this site — the real data wins.
    onair_vendor_by_site_code = {"S1": "ZTE"}
    assert (
        IncidentSyncService._resolve_vendor_name("S1", 20, onair_vendor_by_site_code) == "ZTE"
    )


def test_resolve_vendor_name_falls_back_to_confirmed_actual_ran_vendor_code():
    # Site not in mssql_site_onair (e.g. Planned/Off-Air) — falls back to
    # the confirmed 3-code check, same as before this change.
    assert IncidentSyncService._resolve_vendor_name("S404", 6, {}) == "ZTE"


def test_resolve_vendor_name_unknown_when_neither_source_has_it():
    assert IncidentSyncService._resolve_vendor_name("S404", 58, {}) == "Unknown"
    assert IncidentSyncService._resolve_vendor_name(None, None, {}) == "Unknown"


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
    rows = [
        _site_down_source_row(**{"Incident Numeric ID": 1}),
        _site_down_source_row(**{"Incident Numeric ID": 2}),
    ]

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
    rows = [
        _site_down_source_row(**{"Site Numeric ID": 10}),
        _site_down_source_row(**{"Site Numeric ID": 20}),
    ]

    result = svc._latest_wo_by_incident_site(rows)

    assert result[(1, 10)]["INC-WO ID"] == "WO-A"
    assert result[(1, 20)]["INC-WO ID"] == "WO-B"


def test_latest_wo_by_incident_site_matches_a_siteless_wo_to_a_singleton_siteless_incident():
    """ "Other Site" incidents (site not in the registered Site list, see
    incident_by_status.sql's COALESCE note) have no Site Numeric ID, and
    neither does their WO — but object_324.parent_incident is a direct FK
    to the incident's own numeric id, so when that incident is a single
    row in this batch (no multi-site fan-out to disambiguate), matching by
    incident id alone is unambiguous. Confirmed live: INC-0000223089 (site
    "I0229", not in object_160) has exactly this shape, and the source
    system's own UI shows its WO directly under the incident."""
    siteless_wo = _wo_row(**{"Site Numeric ID": None, "INC-WO ID": "WO-SHOULD-MATCH"})
    repo = FakeIncidentRepoForWo([siteless_wo])
    svc = IncidentSyncService(incident_repository=repo)
    rows = [_site_down_source_row(**{"Site Numeric ID": None})]

    result = svc._latest_wo_by_incident_site(rows)

    assert result[(1, None)]["INC-WO ID"] == "WO-SHOULD-MATCH"


def test_latest_wo_by_incident_site_still_refuses_a_siteless_wo_when_the_incident_has_multiple_rows():
    """The real protection the original guard existed for: a multi-site
    incident where more than one of its sites fails to resolve produces
    several siteless rows for the SAME incident id — there's no way to
    tell which row a siteless WO actually belongs to, so it must stay
    unmatched for all of them, same as before this fix."""
    siteless_wo = _wo_row(**{"Site Numeric ID": None, "INC-WO ID": "WO-SHOULD-NOT-MATCH"})
    repo = FakeIncidentRepoForWo([siteless_wo])
    svc = IncidentSyncService(incident_repository=repo)
    rows = [
        _site_down_source_row(**{"Site Numeric ID": None, "Site Code": "UNRESOLVED-A"}),
        _site_down_source_row(**{"Site Numeric ID": None, "Site Code": "UNRESOLVED-B"}),
    ]

    result = svc._latest_wo_by_incident_site(rows)

    assert (1, None) not in result


def test_latest_wo_by_incident_site_never_cross_matches_two_different_siteless_incidents():
    """Real bug found live (INC-0000122533/INC-0000118176) — two different
    "Other Site" incidents, each its own singleton siteless row, each with
    its own siteless WO. The (incident_id, site_id) key already keeps them
    apart since the incident ids differ; each must get only its own WO,
    never the other's."""
    wo_a = _wo_row(**{"Incident Numeric ID": 1, "Site Numeric ID": None, "INC-WO ID": "WO-A"})
    wo_b = _wo_row(**{"Incident Numeric ID": 2, "Site Numeric ID": None, "INC-WO ID": "WO-B"})
    repo = FakeIncidentRepoForWo([wo_a, wo_b])
    svc = IncidentSyncService(incident_repository=repo)
    rows = [
        _site_down_source_row(**{"Incident Numeric ID": 1, "Site Numeric ID": None}),
        _site_down_source_row(**{"Incident Numeric ID": 2, "Site Numeric ID": None}),
    ]

    result = svc._latest_wo_by_incident_site(rows)

    assert result[(1, None)]["INC-WO ID"] == "WO-A"
    assert result[(2, None)]["INC-WO ID"] == "WO-B"
