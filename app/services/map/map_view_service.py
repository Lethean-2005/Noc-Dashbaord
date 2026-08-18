"""Business logic for the Map View page (app/routes/map_view.py) — plots
every Site with a real, non-zero lat/lon on a Leaflet map (see
app/static/js/map-view.js).

Reads the already-synced site_cache (app/repositories/site/site_cache_repository.py,
app/database/queries/site_cache.sql) instead of querying Postgres directly —
same cache the rest of the dashboard already reads, kept fresh every
SITE_SYNC_INTERVAL_SECONDS. p_lat/p_lon come straight from Postgres'
object_160.p_lat/p_lon — a handful of sites have no coordinates recorded
there yet (NULL) or a placeholder 0/0, both excluded here since plotting
them would either error or show a marker sitting in the ocean off the
coast of Africa (0,0 — "Null Island").

NMS (the site's network vendor — Nokia/Huawei/ZTE) isn't a site_cache
column at all — same real-vendor-name resolution
app/services/incident/incident_sync_service.py's own _nms_by_site() does:
read the local ne_nms_lookup_cache (site_code -> raw vendor code, synced
independently by SiteSyncService), matched against site_cache.standard_code
(the short numeric code, e.g. "1833" for site "TH1833" — NOT site_cache.name,
which is the full prefixed code and doesn't match ne_nms_lookup_cache.site_code
at all), then mapped through the same shared NMS_NAMES code->vendor-name
table every other NMS-displaying feature in this app uses.
"""

from app.repositories.site.ne_nms_lookup_cache_repository import NeNmsLookupCacheRepository
from app.repositories.site.site_cache_repository import SiteCacheRepository
from app.utils.nms import NMS_NAMES

_SITE_TABLE = "site_cache"
_NE_NMS_LOOKUP_TABLE = "ne_nms_lookup_cache"


def _has_valid_coordinates(row):
    lat, lon = row.get("p_lat"), row.get("p_lon")
    return lat is not None and lon is not None and not (lat == 0 and lon == 0)


class MapViewService:
    def __init__(self, site_cache_repository=None, ne_nms_lookup_cache_repository=None):
        self.site_cache_repository = site_cache_repository or SiteCacheRepository()
        self.ne_nms_lookup_cache_repository = (
            ne_nms_lookup_cache_repository or NeNmsLookupCacheRepository()
        )

    def _nms_by_standard_code(self):
        """standard_code -> real vendor name (e.g. "1833" -> "Nokia") —
        same lookup/mapping IncidentSyncService._nms_by_site() does, just
        keyed by site_cache's own standard_code column instead of the
        "Site Code" key those other rows use."""
        rows = self.ne_nms_lookup_cache_repository.fetch_all(_NE_NMS_LOOKUP_TABLE)
        return {r["site_code"]: NMS_NAMES.get(str(r["nms_code"] or "").strip(), "") for r in rows}

    def get_sites(self):
        """Every site with a real lat/lon, as plain dicts ready for
        Jinja's |tojson — only the fields the map popup/search actually
        use. `name` is the site CODE (e.g. "TH1833" — site_cache.name),
        `site_name` is the human-readable name (site_cache.fra_site_name)
        — the map's search box (map-view.js) matches against both."""
        rows = self.site_cache_repository.fetch_all(_SITE_TABLE)
        nms_by_standard_code = self._nms_by_standard_code()
        return [
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "site_name": row.get("fra_site_name"),
                "status": row.get("status"),
                "site_grade": row.get("site_grade"),
                "province": row.get("province"),
                "district": row.get("district"),
                "commune": row.get("commune"),
                "hub_site": row.get("hub_site"),
                "nms": nms_by_standard_code.get(row.get("standard_code"), ""),
                "lat": row.get("p_lat"),
                "lon": row.get("p_lon"),
            }
            for row in rows
            if _has_valid_coordinates(row)
        ]

    @staticmethod
    def get_status_counts(sites):
        """{"all": N, "on_air": N, "planned": N, "other": N} — one pass
        over the already-fetched site list, matching map-view.js's own
        matchesFilter() classification ("other" = anything that isn't
        on_air/planned) exactly, so the status dropdown's counts and the
        map's own filtering never disagree. Previously done as 3 separate
        Jinja selectattr/rejectattr passes in map/index.html — same
        result, but 3 full list materializations over ~4,300 rows just to
        count them, instead of the one pass here."""
        counts = {"all": len(sites), "on_air": 0, "planned": 0, "other": 0}
        for site in sites:
            status = site.get("status")
            if status == "on_air":
                counts["on_air"] += 1
            elif status == "planned":
                counts["planned"] += 1
            else:
                counts["other"] += 1
        return counts
