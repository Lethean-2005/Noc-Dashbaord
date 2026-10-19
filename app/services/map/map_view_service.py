"""Business logic for the Map View page — plots sites with a real lat/lon
on a Leaflet map (see app/static/js/map-view.js).

Sites with no coordinates or a 0/0 placeholder are excluded ("Null Island").
NMS and is_down are joined via site_cache.standard_code, not site_cache.name
(name is the full prefixed code, e.g. "TH1833" — it won't match).

On-Air sites are sourced from MSSQL ONLY (mssql_site_onair — TBL_SITE
joined to TBL_NE, see app/database/queries/mssql_site.sql), which gives a
real per-site VENDOR straight from NE inventory instead of guessing via
actual_ran_vendor codes. Planned/Other sites still come from Postgres's
site_cache — TBL_SITE has no equivalent status for them (only On
Air/Off Air, confirmed 2026-08-28).

No Postgres fallback for On-Air: a site_cache row with status='on_air'
that MSSQL doesn't know about (confirmed 2026-08-28 — ~93 sites, mostly
never entered into TBL_SITE, a handful where MSSQL itself has them
marked Off Air) is simply not shown as on-air — MSSQL is the sole source
of truth for that status, not a hint layered on top of Postgres's own.

The two sources are otherwise fully independent, on purpose (confirmed
2026-08-28): Planned/Other always match Postgres's own counts exactly,
On-Air always matches MSSQL's own count exactly — neither one is
adjusted to avoid disagreeing with the other. If MSSQL already shows a
site as on-air while Postgres still has it tagged 'planned' (its own
status hasn't caught up yet — ~21 sites seen), that site is plotted
TWICE: once as On Air (from MSSQL), once as Planned (from Postgres) —
the disagreement is left visible on the map rather than one source
silently overriding the other."""

from app.repositories.incident.incident_site_down_cache_repository import (
    IncidentSiteDownCacheRepository,
)
from app.repositories.pop.pop_cache_repository import PopCacheRepository
from app.repositories.site.mssql_site_onair_cache_repository import (
    MssqlSiteOnairCacheRepository,
)
from app.repositories.site.site_cache_repository import SiteCacheRepository
from app.repositories.site.site_ran_vendor_cache_repository import SiteRanVendorCacheRepository
from app.utils.nms import NMS_NAMES, resolve_nms_code_by_site

_SITE_TABLE = "site_cache"
_SITE_RAN_VENDOR_TABLE = "site_ran_vendor_cache"
_INCIDENT_SITE_DOWN_TABLE = "incident_site_down"
_POP_TABLE = "pop_cache"
_MSSQL_SITE_ONAIR_TABLE = "mssql_site_onair"


def _has_valid_coordinates(row, lat_key="p_lat", lon_key="p_lon"):
    lat, lon = row.get(lat_key), row.get(lon_key)
    return lat is not None and lon is not None and not (lat == 0 and lon == 0)


class MapViewService:
    def __init__(
        self,
        site_cache_repository=None,
        incident_site_down_cache_repository=None,
        pop_cache_repository=None,
        site_ran_vendor_cache_repository=None,
        mssql_site_onair_cache_repository=None,
    ):
        self.site_cache_repository = site_cache_repository or SiteCacheRepository()
        self.site_ran_vendor_cache_repository = (
            site_ran_vendor_cache_repository or SiteRanVendorCacheRepository()
        )
        self.incident_site_down_cache_repository = (
            incident_site_down_cache_repository or IncidentSiteDownCacheRepository()
        )
        self.pop_cache_repository = pop_cache_repository or PopCacheRepository()
        self.mssql_site_onair_cache_repository = (
            mssql_site_onair_cache_repository or MssqlSiteOnairCacheRepository()
        )

    def _nms_by_standard_code(self):
        """standard_code -> real vendor name, e.g. "1833" -> "Nokia". Only
        used for Planned/Other sites now — On-Air sites get their vendor
        straight from mssql_site_onair's own VENDOR column (real NE
        inventory data, no guessing needed) instead. Confirmed
        actual_ran_vendor codes ONLY (use_ne_fallback=False) — unlike
        incident_sync_service.py, the Map page's vendor counts get
        compared directly against Streamline's own "Actual RAN Vendor"
        filter counts, and the NE-lookup fallback tier doesn't always
        agree with that field (confirmed 2026-08-27 — see
        app/utils/nms.py's resolve_nms_code_by_site() docstring). A site
        with no confirmed code shows no vendor here rather than a guess
        that might not match Streamline's own count."""
        vendor_rows = self.site_ran_vendor_cache_repository.fetch_all(_SITE_RAN_VENDOR_TABLE)
        nms_by_site = resolve_nms_code_by_site([], vendor_rows, use_ne_fallback=False)
        return {code: NMS_NAMES.get(str(nms or "").strip(), "") for code, nms in nms_by_site.items()}

    def _down_info_by_standard_code(self):
        """standard_code -> {incident_id, occurred_at} for sites with a
        currently-open Site Down incident — same incident_site_down cache
        the "Current Site Down" card reads. A site with more than one open
        incident just keeps the first row seen."""
        rows = self.incident_site_down_cache_repository.fetch_all(_INCIDENT_SITE_DOWN_TABLE)
        down = {}
        for r in rows:
            code = r.get("site_code")
            if code and code not in down:
                down[code] = {
                    "incident_id": r.get("incident_id"),
                    "incident_numeric_id": r.get("incident_numeric_id"),
                    "occurred_at": r.get("occurred_at"),
                }
        return down

    def get_pops(self):
        """Every POP with a real lat/lon, as plain dicts for Jinja's |tojson.
        "code" here is TBL_POP.NCODE, not TBL_POP.CODE — NCODE is the value
        isp_pop_alarm_cache.pop_code actually joins against (see
        alarms.sql), so it's the code that matches how POPs are identified
        elsewhere in this app. "active" is the source's own True/blank
        string flag, converted to a real boolean here — the ISP filter's
        "On Air" option (map-view.js) reads this the same way site.status
        does for real sites."""
        rows = self.pop_cache_repository.fetch_all(_POP_TABLE)
        return [
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "code": row.get("ncode"),
                "province": row.get("province"),
                "district": row.get("district"),
                "commune": row.get("commune"),
                "type": row.get("type"),
                "pro_owner": row.get("pro_owner"),
                "active": row.get("active") == "True",
                "lat": row.get("lat"),
                "lon": row.get("long"),
            }
            for row in rows
            if _has_valid_coordinates(row, "lat", "long")
        ]
    
    def get_sites(self):
        """Every site with a real lat/lon, as plain dicts for Jinja's
        |tojson. On-Air sites come from mssql_site_onair (MSSQL) only —
        Planned/Other come from Postgres's site_cache, minus rows
        claiming 'on_air' itself (no Postgres fallback for that status —
        see this class's own docstring). The two sources are otherwise
        independent — a site both consider theirs (MSSQL: on-air,
        Postgres: still planned) is plotted once per source, not
        deduplicated."""
        postgres_rows = self.site_cache_repository.fetch_all(_SITE_TABLE)
        onair_rows = self.mssql_site_onair_cache_repository.fetch_all(_MSSQL_SITE_ONAIR_TABLE)
        # Postgres backfill for the two fields TBL_SITE doesn't have at
        # all (commune, hub_site) — blank for the small set of on-air
        # sites MSSQL knows about that Postgres doesn't (confirmed
        # 2026-08-28: 48 of 3,716 codes), same "blank over a guess"
        # stance as everywhere else this session.
        postgres_by_code = {
            row["standard_code"]: row for row in postgres_rows if row.get("standard_code")
        }
        nms_by_standard_code = self._nms_by_standard_code()
        down_by_standard_code = self._down_info_by_standard_code()

        sites = []

        for row in onair_rows:
            if not _has_valid_coordinates(row, "lat", "long"):
                continue
            code = row.get("site_code")
            backfill = postgres_by_code.get(code) or {}
            down = down_by_standard_code.get(code)
            sites.append(
                {
                    "id": code,
                    "name": code,
                    "site_name": row.get("site_name"),
                    "status": "on_air",
                    "site_grade": row.get("site_grade"),
                    "province": row.get("province"),
                    "district": row.get("district"),
                    "commune": backfill.get("commune") or "",
                    "village": row.get("village"),
                    "hub_site": backfill.get("hub_site") or "",
                    "nms": row.get("vendor") or "",
                    "is_down": down is not None,
                    "incident_id": (down or {}).get("incident_id") or "",
                    "incident_numeric_id": (down or {}).get("incident_numeric_id") or "",
                    "occurred_at": (down or {}).get("occurred_at") or "",
                    "lat": row.get("lat"),
                    "lon": row.get("long"),
                    "pro_owner": None,
                }
            )

        for row in postgres_rows:
            code = row.get("standard_code")
            # No Postgres fallback for on_air — MSSQL is the sole source
            # of truth for that status now, not a hint Postgres can add
            # to. A site_cache row claiming on_air that MSSQL doesn't
            # know about is simply not shown as on-air.
            #
            # Otherwise fully independent from MSSQL on purpose (see this
            # class's own docstring) — a site MSSQL already shows as
            # on-air but Postgres still has as 'planned' plots TWICE
            # (once per source) rather than one silently overriding the
            # other.
            if row.get("status") == "on_air":
                continue
            if not _has_valid_coordinates(row):
                continue
            down = down_by_standard_code.get(code)
            sites.append(
                {
                    "id": row.get("id"),
                    "name": row.get("name"),
                    # physical_location_name is object_308.name, the real
                    # Physical Location code (e.g. "KAB_SROV_TOCH") — not
                    # sites.fra_site_name, a separate mixed-case field.
                    "site_name": row.get("physical_location_name"),
                    "status": row.get("status"),
                    "site_grade": row.get("site_grade"),
                    "province": row.get("province"),
                    "district": row.get("district"),
                    "commune": row.get("commune"),
                    "village": row.get("village"),
                    "hub_site": row.get("hub_site"),
                    "nms": nms_by_standard_code.get(code, ""),
                    "is_down": down is not None,
                    "incident_id": (down or {}).get("incident_id") or "",
                    "incident_numeric_id": (down or {}).get("incident_numeric_id") or "",
                    "occurred_at": (down or {}).get("occurred_at") or "",
                    "lat": row.get("p_lat"),
                    "lon": row.get("p_lon"),
                    "pro_owner": row.get("pro_owner"),
                }
            )

        return sites
    
    @staticmethod
    def get_status_counts(sites):
        """{"all": N, "on_air": N, "planned": N, "other": N, "site_down": N} —
        site_down is orthogonal, counted separately from on_air/planned/other."""
        counts = {"all": len(sites), "on_air": 0, "planned": 0, "other": 0, "site_down": 0}
        for site in sites:
            status = site.get("status")
            if status == "on_air":
                counts["on_air"] += 1
            elif status == "planned":
                counts["planned"] += 1
            else:
                counts["other"] += 1
            if site.get("is_down"):
                counts["site_down"] += 1
        return counts