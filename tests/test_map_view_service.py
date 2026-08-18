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


class FakeNeNmsLookupCacheRepo:
    def __init__(self, rows=None):
        self._rows = rows or []

    def fetch_all(self, table):
        return self._rows


def _site_row(id, **overrides):
    row = {
        "id": id,
        "name": f"Site {id}",
        "fra_site_name": f"Village {id}",
        "standard_code": str(id),
        "status": "on_air",
        "site_grade": "gold",
        "province": "Phnom Penh",
        "district": "Chamkarmon",
        "commune": "Tonle Bassac",
        "hub_site": "Hub A",
        "p_lat": 11.55,
        "p_lon": 104.91,
    }
    row.update(overrides)
    return row


def test_sites_with_valid_coordinates_are_included(app):
    with app.app_context():
        repo = FakeSiteCacheRepo([_site_row(1)])
        sites = MapViewService(repo, FakeNeNmsLookupCacheRepo()).get_sites()

        assert len(sites) == 1
        assert sites[0]["lat"] == 11.55
        assert sites[0]["lon"] == 104.91


def test_sites_with_null_coordinates_are_excluded(app):
    with app.app_context():
        repo = FakeSiteCacheRepo(
            [_site_row(1, p_lat=None, p_lon=None), _site_row(2, p_lat=None, p_lon=104.91)]
        )
        sites = MapViewService(repo, FakeNeNmsLookupCacheRepo()).get_sites()

        assert sites == []


def test_sites_with_zero_zero_coordinates_are_excluded(app):
    """0,0 is a valid float pair but not a real place ("Null Island") —
    it's what a missing coordinate often looks like from an upstream
    system that defaults unset numeric fields to 0 rather than NULL."""
    with app.app_context():
        repo = FakeSiteCacheRepo([_site_row(1, p_lat=0, p_lon=0)])
        sites = MapViewService(repo, FakeNeNmsLookupCacheRepo()).get_sites()

        assert sites == []


def test_zero_latitude_alone_is_still_valid(app):
    """The equator (lat=0) is a real place — only lat AND lon both being 0
    together is the "missing data" signal, not lat=0 alone."""
    with app.app_context():
        repo = FakeSiteCacheRepo([_site_row(1, p_lat=0, p_lon=104.91)])
        sites = MapViewService(repo, FakeNeNmsLookupCacheRepo()).get_sites()

        assert len(sites) == 1


def test_returned_shape_only_includes_map_relevant_fields(app):
    with app.app_context():
        repo = FakeSiteCacheRepo(
            [_site_row(1, name="PP2233", fra_site_name="Kab Srov Toch", standard_code="2233")]
        )
        sites = MapViewService(repo, FakeNeNmsLookupCacheRepo()).get_sites()

        assert sites[0] == {
            "id": 1,
            "name": "PP2233",
            "site_name": "Kab Srov Toch",
            "status": "on_air",
            "site_grade": "gold",
            "province": "Phnom Penh",
            "district": "Chamkarmon",
            "commune": "Tonle Bassac",
            "hub_site": "Hub A",
            "nms": "",
            "lat": 11.55,
            "lon": 104.91,
        }


def test_nms_resolved_via_standard_code_and_vendor_name_map(app):
    """ne_nms_lookup_cache is keyed by the short numeric standard_code
    (e.g. "1833" for site "TH1833"), not the full site name/code — and its
    nms_code ("7") maps through the shared NMS_NAMES table to a real
    vendor name ("Nokia"), same as IncidentSyncService does elsewhere."""
    with app.app_context():
        site_repo = FakeSiteCacheRepo([_site_row(1, name="TH1833", standard_code="1833")])
        nms_repo = FakeNeNmsLookupCacheRepo([{"site_code": "1833", "nms_code": "7"}])

        sites = MapViewService(site_repo, nms_repo).get_sites()

        assert sites[0]["nms"] == "Nokia"


def test_nms_blank_when_standard_code_has_no_lookup_row(app):
    with app.app_context():
        site_repo = FakeSiteCacheRepo([_site_row(1, standard_code="9999")])
        nms_repo = FakeNeNmsLookupCacheRepo([{"site_code": "1833", "nms_code": "7"}])

        sites = MapViewService(site_repo, nms_repo).get_sites()

        assert sites[0]["nms"] == ""


def test_nms_blank_when_lookup_row_has_no_vendor_code(app):
    """A site can have an NE row in ne_nms_lookup_cache with no nms_code
    recorded yet (NULL) — same as the real data seen in this cache."""
    with app.app_context():
        site_repo = FakeSiteCacheRepo([_site_row(1, standard_code="0001")])
        nms_repo = FakeNeNmsLookupCacheRepo([{"site_code": "0001", "nms_code": None}])

        sites = MapViewService(site_repo, nms_repo).get_sites()

        assert sites[0]["nms"] == ""


def test_get_status_counts_matches_map_view_js_classification():
    """"other" is everything that isn't on_air/planned — same rule
    map-view.js's own matchesFilter() uses, so the dropdown's counts and
    the map's actual filtering can never disagree."""
    sites = [
        {"status": "on_air"},
        {"status": "on_air"},
        {"status": "planned"},
        {"status": "ready_for_installation"},
        {"status": None},
    ]

    counts = MapViewService.get_status_counts(sites)

    assert counts == {"all": 5, "on_air": 2, "planned": 1, "other": 2}


def test_get_status_counts_with_no_sites():
    assert MapViewService.get_status_counts([]) == {
        "all": 0,
        "on_air": 0,
        "planned": 0,
        "other": 0,
    }
