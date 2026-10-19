"""Tests for the Map View page's site-filtering logic — only rows with a
real, non-zero p_lat/p_lon should ever reach the map (a NULL or 0/0
coordinate would either error in Leaflet or plot a marker at "Null
Island") — and its NMS vendor-name resolution, which mirrors
IncidentSyncService._nms_by_site() but keyed by site_cache.standard_code.
"""

from app.services.map.map_view_service import MapViewService


class FakeSiteCacheRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self, table):
        return self._rows


class FakeSiteRanVendorCacheRepo:
    def __init__(self, rows=None):
        self._rows = rows or []

    def fetch_all(self, table):
        return self._rows


class FakeIncidentSiteDownRepo:
    def __init__(self, rows=None):
        self._rows = rows or []

    def fetch_all(self, table):
        return self._rows


class FakeMssqlSiteOnairCacheRepo:
    def __init__(self, rows=None):
        self._rows = rows or []

    def fetch_all(self, table):
        return self._rows


def _onair_row(site_code, **overrides):
    row = {
        "site_code": site_code,
        "site_name": f"SITE_{site_code}",
        "province": "Phnom Penh",
        "district": "Doun Penh",
        "village": None,
        "lat": 11.55,
        "long": 104.91,
        "bts_room": "Indoor",
        "link_type": "H-R",
        "site_grade": "Gold",
        "site_type": "RT",
        "location": "Some address",
        "vendor": "Huawei",
    }
    row.update(overrides)
    return row


def _site_row(id, **overrides):
    row = {
        "id": id,
        "name": f"Site {id}",
        "physical_location_name": f"Village {id}",
        "standard_code": str(id),
        "status": "planned",
        "site_grade": "gold",
        "province": "Phnom Penh",
        "district": "Chamkarmon",
        "commune": "Tonle Bassac",
        "village": "Boeung Trabek",
        "hub_site": "Hub A",
        "p_lat": 11.55,
        "p_lon": 104.91,
    }
    row.update(overrides)
    return row


def test_sites_with_valid_coordinates_are_included(app):
    with app.app_context():
        repo = FakeSiteCacheRepo([_site_row(1)])
        service = MapViewService(repo, FakeIncidentSiteDownRepo())
        sites = service.get_sites()

        assert len(sites) == 1
        assert sites[0]["lat"] == 11.55
        assert sites[0]["lon"] == 104.91


def test_sites_with_null_coordinates_are_excluded(app):
    with app.app_context():
        repo = FakeSiteCacheRepo(
            [_site_row(1, p_lat=None, p_lon=None), _site_row(2, p_lat=None, p_lon=104.91)]
        )
        service = MapViewService(repo, FakeIncidentSiteDownRepo())
        sites = service.get_sites()

        assert sites == []


def test_sites_with_zero_zero_coordinates_are_excluded(app):
    """0,0 is a valid float pair but not a real place ("Null Island") —
    it's what a missing coordinate often looks like from an upstream
    system that defaults unset numeric fields to 0 rather than NULL."""
    with app.app_context():
        repo = FakeSiteCacheRepo([_site_row(1, p_lat=0, p_lon=0)])
        service = MapViewService(repo, FakeIncidentSiteDownRepo())
        sites = service.get_sites()

        assert sites == []


def test_zero_latitude_alone_is_still_valid(app):
    """The equator (lat=0) is a real place — only lat AND lon both being 0
    together is the "missing data" signal, not lat=0 alone."""
    with app.app_context():
        repo = FakeSiteCacheRepo([_site_row(1, p_lat=0, p_lon=104.91)])
        service = MapViewService(repo, FakeIncidentSiteDownRepo())
        sites = service.get_sites()

        assert len(sites) == 1


def test_returned_shape_only_includes_map_relevant_fields(app):
    with app.app_context():
        repo = FakeSiteCacheRepo(
            [_site_row(1, name="PP2233", physical_location_name="KAB_SROV_TOCH", standard_code="2233")]
        )
        service = MapViewService(repo, FakeIncidentSiteDownRepo())
        sites = service.get_sites()

        assert sites[0] == {
            "id": 1,
            "name": "PP2233",
            "site_name": "KAB_SROV_TOCH",
            "status": "planned",
            "site_grade": "gold",
            "province": "Phnom Penh",
            "district": "Chamkarmon",
            "commune": "Tonle Bassac",
            "village": "Boeung Trabek",
            "hub_site": "Hub A",
            "nms": "",
            "is_down": False,
            "incident_id": "",
            "incident_numeric_id": "",
            "occurred_at": "",
            "lat": 11.55,
            "lon": 104.91,
            "pro_owner": None,
        }


def test_nms_blank_when_no_confirmed_vendor_code(app):
    """The Map page resolves NMS from confirmed actual_ran_vendor codes
    ONLY (use_ne_fallback=False, see MapViewService._nms_by_standard_code())
    — unlike IncidentSyncService, which still uses an NE-lookup fallback.
    A site with no confirmed actual_ran_vendor code shows no vendor here
    at all, confirmed 2026-08-27 after the Map's on-air vendor counts
    didn't exactly match Streamline's own filtered counts while a
    fallback was still on."""
    with app.app_context():
        site_repo = FakeSiteCacheRepo([_site_row(1, name="TH1833", standard_code="1833")])

        sites = MapViewService(
            site_repo, FakeIncidentSiteDownRepo(), site_ran_vendor_cache_repository=FakeSiteRanVendorCacheRepo()
        ).get_sites()

        assert sites[0]["nms"] == ""


def test_nms_from_confirmed_actual_ran_vendor_code(app):
    """See app/utils/nms.py for how 20 (not the earlier, wrongly-trusted
    22) was confirmed as Huawei — an exact-count match against
    Streamline's own "Actual RAN Vendor" filter."""
    with app.app_context():
        site_repo = FakeSiteCacheRepo([_site_row(1, standard_code="1439")])
        vendor_repo = FakeSiteRanVendorCacheRepo([{"site_code": "1439", "actual_ran_vendor": 20}])

        sites = MapViewService(
            site_repo, FakeIncidentSiteDownRepo(), site_ran_vendor_cache_repository=vendor_repo
        ).get_sites()

        assert sites[0]["nms"] == "Huawei"


def test_nms_ignores_unconfirmed_actual_ran_vendor_code(app):
    """Code 58 isn't in ACTUAL_RAN_VENDOR_TO_NMS_CODE (still unconfirmed —
    see app/utils/nms.py). The Map page has no NE-lookup fallback to fall
    back to either (use_ne_fallback=False) — an unconfirmed code shows no
    vendor at all here, rather than a guess."""
    with app.app_context():
        site_repo = FakeSiteCacheRepo([_site_row(1, standard_code="0723")])
        vendor_repo = FakeSiteRanVendorCacheRepo([{"site_code": "0723", "actual_ran_vendor": 58}])

        sites = MapViewService(
            site_repo, FakeIncidentSiteDownRepo(), site_ran_vendor_cache_repository=vendor_repo
        ).get_sites()

        assert sites[0]["nms"] == ""


def test_is_down_true_when_standard_code_has_an_open_site_down_incident(app):
    """incident_site_down (the same cache behind the "Current Site Down"
    drilldown/card) is keyed by the short numeric site_code, matched
    against site_cache.standard_code — same key format NMS resolution
    uses, not site_cache.name."""
    with app.app_context():
        site_repo = FakeSiteCacheRepo([_site_row(1, name="TH1833", standard_code="1833")])
        down_repo = FakeIncidentSiteDownRepo([{"site_code": "1833"}])

        sites = MapViewService(site_repo, down_repo).get_sites()

        assert sites[0]["is_down"] is True


def test_is_down_false_when_no_matching_incident(app):
    with app.app_context():
        site_repo = FakeSiteCacheRepo([_site_row(1, standard_code="9999")])
        down_repo = FakeIncidentSiteDownRepo([{"site_code": "1833"}])

        sites = MapViewService(site_repo, down_repo).get_sites()

        assert sites[0]["is_down"] is False


def test_is_down_false_with_empty_incident_site_down_cache(app):
    with app.app_context():
        site_repo = FakeSiteCacheRepo([_site_row(1)])

        sites = MapViewService(site_repo, FakeIncidentSiteDownRepo()).get_sites()

        assert sites[0]["is_down"] is False


def test_onair_site_comes_from_mssql_with_vendor_as_nms(app):
    """On-Air sites are built from mssql_site_onair, not site_cache — nms
    comes straight from its own VENDOR column (real NE inventory), no
    actual_ran_vendor code resolution involved."""
    with app.app_context():
        onair_repo = FakeMssqlSiteOnairCacheRepo([_onair_row("0001", vendor="Nokia")])

        sites = MapViewService(
            FakeSiteCacheRepo([]),
            FakeIncidentSiteDownRepo(),
            mssql_site_onair_cache_repository=onair_repo,
        ).get_sites()

        assert len(sites) == 1
        assert sites[0]["id"] == "0001"
        assert sites[0]["name"] == "0001"
        assert sites[0]["site_name"] == "SITE_0001"
        assert sites[0]["status"] == "on_air"
        assert sites[0]["nms"] == "Nokia"
        assert sites[0]["lat"] == 11.55
        assert sites[0]["lon"] == 104.91


def test_onair_site_backfills_commune_and_hub_site_from_postgres(app):
    """TBL_SITE has neither commune nor hub_site — pulled from site_cache
    by standard_code when the same site exists there too."""
    with app.app_context():
        pg_repo = FakeSiteCacheRepo(
            [_site_row(1, standard_code="0001", commune="Tonle Bassac", hub_site="Hub A")]
        )
        onair_repo = FakeMssqlSiteOnairCacheRepo([_onair_row("0001")])

        sites = MapViewService(
            pg_repo,
            FakeIncidentSiteDownRepo(),
            mssql_site_onair_cache_repository=onair_repo,
        ).get_sites()

        assert sites[0]["commune"] == "Tonle Bassac"
        assert sites[0]["hub_site"] == "Hub A"


def test_onair_site_commune_and_hub_site_blank_when_not_in_postgres(app):
    """A SITE_CODE MSSQL knows about that Postgres doesn't (confirmed
    2026-08-28: 48 of 3,716 codes) shows blank rather than a guess."""
    with app.app_context():
        onair_repo = FakeMssqlSiteOnairCacheRepo([_onair_row("9999")])

        sites = MapViewService(
            FakeSiteCacheRepo([]),
            FakeIncidentSiteDownRepo(),
            mssql_site_onair_cache_repository=onair_repo,
        ).get_sites()

        assert sites[0]["commune"] == ""
        assert sites[0]["hub_site"] == ""


def test_postgres_row_plotted_separately_when_mssql_disagrees(app):
    """The two sources are independent, on purpose — Planned always
    matches Postgres's own count exactly, On-Air always matches MSSQL's
    own count exactly. A site MSSQL already shows as on-air but Postgres
    still has as 'planned' (its status hasn't caught up yet) is plotted
    TWICE, once per source, rather than one silently overriding the
    other (confirmed 2026-08-28, after Planned undercounted Streamline's
    own filter by exactly the sites this affected)."""
    with app.app_context():
        pg_repo = FakeSiteCacheRepo([_site_row(1, standard_code="0001", status="planned")])
        onair_repo = FakeMssqlSiteOnairCacheRepo([_onair_row("0001")])

        sites = MapViewService(
            pg_repo,
            FakeIncidentSiteDownRepo(),
            mssql_site_onair_cache_repository=onair_repo,
        ).get_sites()

        assert len(sites) == 2
        statuses = {s["status"] for s in sites}
        assert statuses == {"on_air", "planned"}
        onair_entry = next(s for s in sites if s["status"] == "on_air")
        planned_entry = next(s for s in sites if s["status"] == "planned")
        assert onair_entry["nms"] == "Huawei"
        assert planned_entry["id"] == 1


def test_postgres_only_site_still_included_when_not_in_mssql_onair(app):
    with app.app_context():
        pg_repo = FakeSiteCacheRepo([_site_row(1, standard_code="5555", status="planned")])
        onair_repo = FakeMssqlSiteOnairCacheRepo([_onair_row("0001")])

        sites = MapViewService(
            pg_repo,
            FakeIncidentSiteDownRepo(),
            mssql_site_onair_cache_repository=onair_repo,
        ).get_sites()

        assert len(sites) == 2
        statuses = {s["status"] for s in sites}
        assert statuses == {"on_air", "planned"}


def test_postgres_on_air_site_excluded_when_not_in_mssql_onair(app):
    """No Postgres fallback for on_air — MSSQL is the sole source of
    truth for that status. A site_cache row claiming on_air that MSSQL
    doesn't know about isn't shown as on-air, or at all (unlike
    planned/other rows, which Postgres alone still fully covers)."""
    with app.app_context():
        pg_repo = FakeSiteCacheRepo([_site_row(1, standard_code="5555", status="on_air")])

        sites = MapViewService(
            pg_repo,
            FakeIncidentSiteDownRepo(),
            mssql_site_onair_cache_repository=FakeMssqlSiteOnairCacheRepo([]),
        ).get_sites()

        assert sites == []


def test_onair_site_with_null_coordinates_excluded(app):
    with app.app_context():
        onair_repo = FakeMssqlSiteOnairCacheRepo(
            [_onair_row("0001", lat=None, long=None), _onair_row("0002", lat=0, long=0)]
        )

        sites = MapViewService(
            FakeSiteCacheRepo([]),
            FakeIncidentSiteDownRepo(),
            mssql_site_onair_cache_repository=onair_repo,
        ).get_sites()

        assert sites == []


def test_get_status_counts_matches_map_view_js_classification():
    """"other" is everything that isn't on_air/planned — same rule
    map-view.js's own matchesFilter() uses, so the dropdown's counts and
    the map's actual filtering can never disagree."""
    sites = [
        {"status": "on_air", "is_down": False},
        {"status": "on_air", "is_down": True},
        {"status": "planned", "is_down": False},
        {"status": "ready_for_installation", "is_down": False},
        {"status": None, "is_down": False},
    ]

    counts = MapViewService.get_status_counts(sites)

    assert counts == {"all": 5, "on_air": 2, "planned": 1, "other": 2, "site_down": 1}


def test_get_status_counts_with_no_sites():
    assert MapViewService.get_status_counts([]) == {
        "all": 0,
        "on_air": 0,
        "planned": 0,
        "other": 0,
        "site_down": 0,
    }
