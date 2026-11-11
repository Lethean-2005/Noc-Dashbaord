"""Site Down 24h Teams alert — two posts per incident, each sent at
most once:

  Stage 1 (down-alert): once a Site Down incident has been active for
  SITE_DOWN_24H_ALERT_THRESHOLD_HOURS (default 24), post a card with
  its details to Teams.

  Stage 2 (restore-confirmation): once that SAME incident actually
  resolves, post a second, separate card confirming it, worded to
  refer back to the down-alert ("the incident report above") rather
  than technically threaded — confirmed against the user's own real
  Teams examples that this is how their existing "Workflows" bot alerts
  already behave; a true threaded reply needs Graph API, which this
  org's Azure admin has disabled app registration for.

site_down_24h_alert_cache (SiteDown24hAlertCacheRepository) is this
feature's own dedup ledger — unlike every alert in webhook/, which
resends its full current list every cycle, each incident here gets
each of these 2 posts exactly once, ever.

Sending reuses webhook.common's own _post_json()/_pool() — same
corporate-firewall-safe TLS handling already proven working for every
other Teams webhook in this app, not a second copy of that logic.
"""

import base64
from html import escape
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import current_app

from app.repositories.incident.incident_repository import IncidentRepository
from app.repositories.incident.incident_site_down_cache_repository import (
    IncidentSiteDownCacheRepository,
)
from app.repositories.incident.site_down_24h_alert_cache_repository import (
    SiteDown24hAlertCacheRepository,
)
from app.repositories.site.mssql_site_onair_cache_repository import (
    MssqlSiteOnairCacheRepository,
)
from app.repositories.site.site_ran_name_cache_repository import SiteRanNameCacheRepository
from app.repositories.site.site_technology_cache_repository import (
    SiteTechnologyCacheRepository,
)
from app.services.postgres_sync_utils import to_local_seconds
from app.repositories.vip.vip_site_cache_repository import VipSiteCacheRepository
from app.services.telegram.telegram_alert import _HAS_OPENPYXL, _build_excel_bytes
from app.utils.logger import get_logger
from webhook.common import _id_link, _post_json

logger = get_logger(__name__)

_SITE_DOWN_TABLE = "incident_site_down"
_SITE_TECHNOLOGY_TABLE = "site_technology_cache"
_VIP_SITE_TABLE = "vip_site_cache"
_RAN_NAME_TABLE = "site_ran_name_cache"
_ONAIR_TABLE = "mssql_site_onair"

# Excel attachment columns for a multi-site incident — exact header names
# and order the user specified (not uppercase for Longitude/Latitude,
# matching their own reference sheet exactly). Built from `sites` rows
# already read for the HTML message, plus 3 extra lookups
# (_build_ran_name_lookup/_build_onair_lookup, alongside the existing
# tech/vip ones) that only this attachment needs.
_EXCEL_COLUMNS = (
    ("№", "_row_number"),
    ("SITE_NAME", "site_name"),
    ("SITE_CODE", "site_code"),
    ("RAN_NAME", "ran_name"),
    ("TECH_SERVICES", "tech_services"),
    ("AFFECTED_SERVICES", "affected_services"),
    ("PROVINCE", "province"),
    ("DISTRICT", "district"),
    ("COMMUNE", "commune"),
    ("SITE_GRADE", "site_grade"),
    ("VIP", "vip"),
    ("Longitude", "longitude"),
    ("Latitude", "latitude"),
)

# Generation order for Services Impacted (e.g. "2G/4G", "2G/3G/4G/5G") —
# fixed order, not alphabetical, so it always reads low-to-high.
_TECH_ORDER = ("2g", "3g", "4g", "5g")

# Same "is this a hub site" convention alarm_site_down_service.py/
# alarm_completely_site_down_service.py already use, reused here so a
# hub reads the same way across every card in this app.
_HUB_SITE_VALUES = {"hub-mw", "hub-router"}

# Hardcoded rather than read from current_app.config["TIMEZONE"] at
# import time — same reasoning as incident_service.py's own _LOCAL_TZ
# (this file's own functions get called from test call sites too).
_LOCAL_TZ = ZoneInfo("Asia/Phnom_Penh")


def _now_local():
    return datetime.now(_LOCAL_TZ)


def _parse_ts(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _format_display_ts(dt):
    """datetime -> '08-Oct-2026 13:35', matching the user's own real
    Teams examples exactly (DD-Mon-YYYY HH:MM)."""
    return dt.strftime("%d-%b-%Y %H:%M")


def _format_duration_ddhhmm(hours_float):
    """2.4666... hours -> '00:02:28' (DD:HH:MM) — matches the user's own
    real restore-confirmation template exactly (verified against their
    own example: 02:21 -> 04:49 is 2h28m, which this formats as
    '00:02:28')."""
    total_minutes = int(round(hours_float * 60))
    days, remainder = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(remainder, 60)
    return f"{days:02d}:{hours:02d}:{minutes:02d}"


def _root_cause_text(actual_root_cause, l1_investigation):
    """Actual Root Cause (set by NOC once the real cause is confirmed) if
    present, else L1 NOC Investigation Result (the initial finding, almost
    always what's available for a still-open Stage 1 down-alert), else
    "Pending investigation" — same fallback shape _action_recovery_text()
    below uses for Resolution/Last Comments."""
    actual = (actual_root_cause or "").strip()
    if actual:
        return actual
    l1 = (l1_investigation or "").strip()
    return l1 if l1 else "Pending investigation"


def _action_recovery_text(resolution, last_comments):
    """Resolution (the confirmed fix, set at formal resolution) if
    present, else Last Comments (NOC's running notes — often the only
    thing available, confirmed live: Resolution is blank on ~75% of
    closed Site Down incidents even after resolution), else "Pending
    investigation"."""
    res = (resolution or "").strip()
    if res:
        return res
    note = (last_comments or "").strip()
    return note if note else "Pending investigation"


def _format_services_impacted(site_code, tech_rows_by_site):
    """'2G/4G', '2G/3G/4G/5G', etc. — fixed generation order, not
    however site_technology_cache happens to list them. Empty string
    (field simply omitted from the message) if this site has no known
    technology inventory at all, rather than a misleading blank line."""
    techs = {t.lower() for t in tech_rows_by_site.get(site_code, [])}
    ordered = [g.upper() for g in _TECH_ORDER if g in techs]
    return "/".join(ordered)


def _format_areas_impacted(sites):
    """Multi-site incidents show unique provinces; one site keeps full location."""
    if len(sites) > 1:
        provinces = []
        seen_provinces = set()
        for site in sites:
            province = str(site.get("province") or "").strip()
            if province and province.casefold() not in seen_provinces:
                provinces.append(province)
                seen_provinces.add(province.casefold())
        return " / ".join(provinces)
    seen = []
    for s in sites:
        parts = []
        if s.get("province"):
            parts.append(f"{s['province']} Pro")
        if s.get("district"):
            parts.append(f"{s['district']} Dis")
        if s.get("commune"):
            parts.append(f"{s['commune']} Com")
        group = ", ".join(parts)
        if group and group not in seen:
            seen.append(group)
    return " | ".join(seen)


def _format_services_impacted_for_sites(site_codes, tech_rows_by_site):
    """Union of technology across every impacted site — a multi-site
    incident's real "services impacted" is everything any of its sites
    actually have, not just whichever site happened to be read first
    (the real bug this replaces: incident_site_down has one row per
    (incident, site), and the old version used only the first row's own
    site, silently dropping every other site's technology AND
    occasionally picking a site with no technology data at all when a
    better-documented sibling site was available)."""
    techs = set()
    for code in site_codes:
        techs.update(t.lower() for t in tech_rows_by_site.get(code, []))
    ordered = [g.upper() for g in _TECH_ORDER if g in techs]
    return "/".join(ordered)


def _build_tech_lookup():
    rows = SiteTechnologyCacheRepository().fetch_all(_SITE_TECHNOLOGY_TABLE)
    lookup = {}
    for r in rows:
        lookup.setdefault(r.get("site_code"), []).append(r.get("technology") or "")
    return lookup


def _build_vip_lookup():
    """{site_code: 'VIP'|'VVIP'} — vip_site_cache only ever holds VIP/
    VVIP sites in the first place (its own MSSQL query is already
    scoped to SITE_STRATEGIC IN ('VIP', 'VVIP')), so a site_code simply
    not appearing here means neither, no extra filtering needed."""
    rows = VipSiteCacheRepository().fetch_all(_VIP_SITE_TABLE)
    return {r.get("site_code"): r.get("site_strategic") for r in rows if r.get("site_code")}


def _build_ran_name_lookup():
    """{site_code: 'NSiKCH1002'} — the multi-site Excel attachment's own
    RAN_NAME column (site_ran_name_cache, synced from MSSQL TBL_NE's
    SRAN — see site_sync_service.py's sync_ran_name())."""
    rows = SiteRanNameCacheRepository().fetch_all(_RAN_NAME_TABLE)
    return {r.get("site_code"): r.get("ran_name") or "" for r in rows if r.get("site_code")}


def _build_onair_lookup():
    """{site_code: {'lat': ..., 'long': ...}} — the multi-site Excel
    attachment's own Longitude/Latitude columns (mssql_site_onair, the
    same MSSQL TBL_SITE cache the dashboard's Map page already reads)."""
    rows = MssqlSiteOnairCacheRepository().fetch_all(_ONAIR_TABLE)
    return {r.get("site_code"): r for r in rows if r.get("site_code")}


def _format_vip_impacted(sites, vip_lookup):
    """Count of impacted sites that are VIP/VVIP, e.g. '1', '2' — matches
    the user's own template (a plain number, not which sites/tiers) — or
    '0' when none of the impacted sites are VIP/VVIP."""
    codes = {s.get("site_code") for s in sites if vip_lookup.get(s.get("site_code"))}
    return str(len(codes))


def _group_by_incident(rows):
    """incident_site_down has one row per (incident, site) — groups
    those back into one entry per incident_id, each carrying its own
    list of site rows, so a multi-site incident is alerted on ONCE with
    every one of its sites represented, not once per site row (or worse,
    only its first site row — see _format_services_impacted_for_sites()'s
    own docstring for the bug this fixes). Preserves first-seen order."""
    groups = {}
    order = []
    for r in rows:
        incident_id = r.get("incident_id")
        if not incident_id:
            continue
        if incident_id not in groups:
            groups[incident_id] = []
            order.append(incident_id)
        # A site may be repeated by joins; count and export it once.
        code = str(r.get("site_code") or "").strip()
        if code and any(str(site.get("site_code") or "").strip() == code
                        for site in groups[incident_id]):
            continue
        groups[incident_id].append(r)
    return [(incident_id, groups[incident_id]) for incident_id in order]


def _earliest_occurred(sites):
    timestamps = [_parse_ts(site.get("occurred_at")) for site in sites]
    return min((value for value in timestamps if value is not None), default=None)


def _hub_site_groups(sites):
    """{hub site name: [its own codes]} for every HUB-flagged site in
    the group (hub_site not "Not Hub") — same _HUB_SITE_VALUES
    convention alarm_site_down_service.py/alarm_completely_site_down_
    service.py already use for "is this a hub", so a hub reads the same
    way across every card in this app. Grouped by name (not one entry
    per code) since one hub location can carry more than one site code
    (confirmed live: DAMBOUK_RUNG has both 1166 and 1234)."""
    groups = {}
    order = []
    for s in sites:
        if (s.get("hub_site") or "").strip().lower() not in _HUB_SITE_VALUES:
            continue
        name = s.get("site_name")
        code = s.get("site_code")
        if not name or not code:
            continue
        if name not in groups:
            groups[name] = []
            order.append(name)
        if code not in groups[name]:
            groups[name].append(code)
    return [(name, groups[name]) for name in order]


def _build_down_alert_title(sites):
    """Keep multi-site titles short; individual site details stay in Excel."""
    if len(sites) == 1:
        s = sites[0]
        return f"Site {s.get('site_name')} ({s.get('site_code')}) down over 24 hrs"
    return f"{len(sites)} Sites down over 24hrs"


def _count_hub_sites(sites):
    return len({
        str(site.get("site_code") or site.get("site_name") or "").strip()
        for site in sites
        if str(site.get("hub_site") or "").strip().lower() in _HUB_SITE_VALUES
        and (site.get("site_code") or site.get("site_name"))
    })


def _build_multi_site_excel(sites, tech_lookup, vip_lookup, ran_name_lookup, onair_lookup):
    """One row per impacted site, per the user's own reference column
    list (№/SITE_NAME/SITE_CODE/RAN_NAME/TECH_SERVICES/
    AFFECTED_SERVICES/PROVINCE/DISTRICT/COMMUNE/SITE_GRADE/VIP/
    Longitude/Latitude) — only built for a multi-site incident (see
    check_and_send_down_alerts()'s own `len(sites) > 1` check); a
    single-site incident's one row is already fully readable in the
    message text itself, no attachment needed.

    TECH_SERVICES and AFFECTED_SERVICES both come from the same
    per-site technology inventory (_format_services_impacted) — this
    app has no per-site, per-technology "which generation actually went
    down at THIS site" signal (only the whole-incident alarm feed), so
    the two columns carry the same value, matching the shape of the
    user's own reference sheet.

    Reuses telegram_alert.py's own _build_excel_bytes (dark-navy header,
    autosize, banded rows — already proven across 4 other alerts) rather
    than a second styling implementation. Returns None if openpyxl isn't
    installed."""
    if not _HAS_OPENPYXL:
        return None

    rows = []
    for i, s in enumerate(sites, start=1):
        code = s.get("site_code")
        onair = onair_lookup.get(code) or {}
        tech_services = _format_services_impacted(code, tech_lookup)
        rows.append({
            "_row_number": i,
            "site_name": s.get("site_name") or "",
            "site_code": code or "",
            "ran_name": ran_name_lookup.get(code) or "",
            "tech_services": tech_services,
            "affected_services": tech_services,
            "province": s.get("province") or "",
            "district": s.get("district") or "",
            "commune": s.get("commune") or "",
            "site_grade": s.get("site_grade") or "",
            "vip": vip_lookup.get(code) or "",
            "longitude": onair.get("long"),
            "latitude": onair.get("lat"),
        })

    return _build_excel_bytes(
        _EXCEL_COLUMNS, rows, "Incident Report - Impacted Sites",
        font_name="Huawei Sans", border_style="thin",
        auto_filter=False, wrap_headers=False, fit_single_line=True,
        show_title=False, header_bold=False,
        left_align={"SITE_NAME", "RAN_NAME", "PROVINCE", "DISTRICT", "COMMUNE"},
    )


def _build_down_alert_html(sites, services, areas, vip_impacted="0"):
    """`sites` is every site row for ONE incident (1 for a single-site
    incident, more for a multi-site one) — all fields below read off
    sites[0] except the ones that genuinely depend on the whole group
    (site names/codes, Number of Site Impact, services, areas, Source,
    VIP/VVIP Impacted)."""
    first = sites[0]
    occurred = _earliest_occurred(sites)
    site_names = ", ".join(dict.fromkeys(s.get("site_name") for s in sites if s.get("site_name")))
    site_codes = ", ".join(dict.fromkeys(s.get("site_code") for s in sites if s.get("site_code")))

    # Ref is always the Incident's own id, never a Work Order ref — the
    # field is labeled "Incident/Work Order Ref" but always carries the
    # Incident side of that now.
    incident_ref = escape(str(first.get("incident_id") or ""))
    link = _id_link(first, "incident_id")
    ref_display = f'<a href="{escape(link, quote=True)}">{incident_ref}</a>' if link else incident_ref

    items = [f"Incident/Work Order Ref: {ref_display}"]
    if len(sites) == 1:
        items.extend([
            f"Site Name: {escape(site_names or '-')}",
            f"Site Code: {escape(site_codes or '-')}",
        ])
    items.append(f"Number of Sites Impacted: {len(sites)}")
    if len(sites) > 1:
        items.append(f"Hub Sites Impacted: {_count_hub_sites(sites)}")
    if services:
        items.append(f"Services Impacted: {escape(services)}")
    if areas:
        items.append(f"Areas Impacted: {escape(areas)}")
    items.append(f"VIP/VVIP Impacted: {escape(str(vip_impacted or '0'))}")
    source = ", ".join(dict.fromkeys(s.get("source") for s in sites if s.get("source")))
    if source:
        items.append(f"Source: {escape(source)}")
    items.append(f"Site Priority: {escape(str(first.get('site_grade') or '-'))}")
    items.append(f"Incident/Outage Start: {_format_display_ts(occurred) if occurred else '-'}")
    root_cause = _root_cause_text(first.get("actual_root_cause"), first.get("l1_noc_investigation_result"))
    items.append(f"Root Cause: {escape(root_cause)}")
    note = (first.get("last_comments") or "").strip()
    if note:
        items.append(f"Note: {escape(note)}")

    li = "".join(f"<li>{i}</li>" for i in items)
    return (
        f"<b>{escape(_build_down_alert_title(sites))}</b><br><br>"
        "Dear All,<br>"
        f"Please be informed that the following {'sites have' if len(sites) > 1 else 'site has'} been down for over 24 hours:"
        f"<ul>{li}</ul>"
        "Best Regards,<br>Work Flow Sitedown-alert"
    )


def _build_restore_alert_html(
    incident_ref, occurred, restored, actual_root_cause, l1_investigation, resolution, last_comments
):
    """Reply body matching the user's restore example; routing ref stays in payload."""
    items = [
        f"Incident/Work Order Ref: {escape(str(incident_ref or '-'))}",
        f"Incident/Outage Start: {_format_display_ts(occurred) if occurred else '-'}",
        f"Restored: {_format_display_ts(restored) if restored else '-'}",
    ]
    if occurred and restored and restored >= occurred:
        items.append(f"Outage Duration(DD:HH:MM): {_format_duration_ddhhmm((restored - occurred).total_seconds() / 3600)}")
    items.append(f"Root Cause: {escape((actual_root_cause or '').strip() or 'Not recorded')}")
    items.append(f"Action Recovery: {escape((resolution or '').strip() or 'Not recorded')}")
    li = "".join(f"<li>{item}</li>" for item in items)
    return (
        "Dear All,<br>"
        "Please be informed that the incident report above has been restored."
        f"<ul>{li}</ul>Best Regards,<br>Work Flow Sitedown-alert"
    )


def _send(html, incident_ref, *, restore=False, excel_bytes=None, excel_filename=None):
    """POSTs {text, incident_ref} to one of two separate Power Automate
    flows/URLs — the down-alert's own flow posts to Teams and saves the
    Message ID into a SharePoint list keyed by incident_ref; the
    restore-confirmation's own SEPARATE flow looks that row up, replies
    in the same thread using it, then deletes the row. Two independent
    flows rather than one flow with a branch (see
    SITE_DOWN_24H_ALERT_RESTORE_WEBHOOK_URL's own config comment for
    why) — `restore` just picks which URL to POST to, nothing else
    differs between the two calls.

    `excel_bytes` (down-alert only, multi-site incidents — see
    _build_multi_site_excel()) is base64-encoded into the same payload
    as `excel_base64`/`excel_filename`, not a second request — Power
    Automate's own "Create file" action can take a base64 string
    directly, same as it already reads `text`/`incident_ref` out of this
    one POST body. The Flow itself still needs its own action added to
    actually create/attach that file in Teams — this only gets the data
    there; it can't configure the Flow on the Power Automate side."""
    config_key = (
        "SITE_DOWN_24H_ALERT_RESTORE_WEBHOOK_URL" if restore else "SITE_DOWN_24H_ALERT_WEBHOOK_URL"
    )
    url = current_app.config[config_key]
    if not url:
        return False, "no URL configured"
    payload = {"text": html, "incident_ref": incident_ref}
    if excel_bytes:
        payload["excel_base64"] = base64.b64encode(excel_bytes).decode("ascii")
        payload["excel_filename"] = excel_filename or "site-down-24h-sites.xlsx"
    try:
        resp = _post_json(url, payload)
        ok = 200 <= resp.status < 300
        return ok, f"HTTP {resp.status}"
    except Exception as exc:
        return False, f"POST error: {exc}"


def check_and_send_down_alerts():
    """Stage 1 — for every currently-active Site Down incident down
    longer than the configured threshold that hasn't been down-alerted
    yet, post the alert (one per incident, every impacted site
    represented — see _group_by_incident()) and record it in the
    ledger. Returns how many were sent."""
    threshold_hours = current_app.config["SITE_DOWN_24H_ALERT_THRESHOLD_HOURS"]
    ledger = SiteDown24hAlertCacheRepository()
    rows = IncidentSiteDownCacheRepository().fetch_all(_SITE_DOWN_TABLE)
    tech_lookup = _build_tech_lookup()
    vip_lookup = _build_vip_lookup()
    ran_name_lookup = _build_ran_name_lookup()
    onair_lookup = _build_onair_lookup()
    now = _now_local().replace(tzinfo=None)

    sent = 0
    for incident_id, sites in _group_by_incident(rows):
        occurred = _earliest_occurred(sites)
        if not occurred:
            continue
        hours_down = (now - occurred).total_seconds() / 3600
        if hours_down < threshold_hours:
            continue
        if ledger.already_down_alerted(incident_id):
            continue

        site_codes = [s.get("site_code") for s in sites if s.get("site_code")]
        services = _format_services_impacted_for_sites(site_codes, tech_lookup)
        areas = _format_areas_impacted(sites)
        vip_impacted = _format_vip_impacted(sites, vip_lookup)
        html = _build_down_alert_html(sites, services, areas, vip_impacted)

        # Only a multi-site incident gets the sheet — one site is already
        # fully readable in the message text itself (see
        # _build_multi_site_excel()'s own docstring).
        excel_bytes = excel_filename = None
        if len(sites) > 1:
            try:
                excel_bytes = _build_multi_site_excel(
                    sites, tech_lookup, vip_lookup, ran_name_lookup, onair_lookup
                )
                if not excel_bytes:
                    raise RuntimeError("Excel workbook could not be generated")
            except Exception:
                logger.exception("Site Down 24h: attachment failed for %s; will retry", incident_id)
                continue
            excel_filename = f"Incident Report {len(sites)} Sites Down - {incident_id}.xlsx"

        ok, reason = _send(html, incident_id, excel_bytes=excel_bytes, excel_filename=excel_filename)
        if ok:
            # Multi-site incident -> one ledger row, first site's own
            # code (debugging/lookup convenience only — dedup is keyed
            # by incident_id, not site_code).
            ledger.mark_down_alerted(incident_id, sites[0].get("site_code"), incident_id)
            sent += 1
            logger.info(f"Site Down 24h: down-alert sent for {incident_id} ({len(sites)} site(s))")
        else:
            logger.error(f"Site Down 24h: down-alert FAILED for {incident_id}: {reason}")
    return sent


def check_and_send_restore_alerts():
    """Stage 2 — for every incident already down-alerted but not yet
    restore-confirmed, check whether it's actually resolved now; if so,
    post the restore-confirmation (tagged with the SAME incident_ref
    Stage 1 used) and record it. Returns how many were sent."""
    ledger = SiteDown24hAlertCacheRepository()
    pending = ledger.pending_restore()
    if not pending:
        return 0
    ref_by_id = dict(pending)
    pending_ids = list(ref_by_id.keys())

    # occurred_at for each pending incident — still readable off
    # incident_site_down if it's still active there (edge case: it
    # cleared the alarm but isn't resolved yet, so it already dropped
    # out of that table); falls back to the restored-row's own data
    # when that's all that's left.
    active_rows = IncidentSiteDownCacheRepository().fetch_all(_SITE_DOWN_TABLE)
    occurred_by_id = {
        r.get("incident_id"): _parse_ts(r.get("occurred_at")) for r in active_rows if r.get("incident_id")
    }

    # fetch_site_down_restored_by_ids() queries Postgres live, straight
    # from object_322 — unlike incident_site_down (active_rows above),
    # it never goes through the sync pipeline's own to_local_seconds()
    # conversion, so these come back as raw UTC datetimes straight off
    # the connection (confirmed: to_local_seconds()'s own docstring —
    # "Postgres hands these back as UTC, no session timezone is set").
    # _parse_ts() only does a naive strptime with no tz math of its own,
    # so without converting here first, "Restored" posted 7 hours early
    # in EVERY restore-confirmation (confirmed live against a real sent
    # message), and "Incident/Outage Start" did too whenever an incident
    # had already cleared its alarm and dropped out of incident_site_down
    # by the time this ran, falling through to this same raw-UTC source.
    resolved_rows = IncidentRepository().fetch_site_down_restored_by_ids(pending_ids)
    sent = 0
    for row in resolved_rows:
        incident_id = row.get("Incident ID")
        restored = _parse_ts(to_local_seconds(row.get("Restored At")))
        if not incident_id or not restored:
            continue
        occurred = _parse_ts(to_local_seconds(row.get("Occurred At"))) or occurred_by_id.get(incident_id)
        if not occurred or restored < occurred:
            logger.warning("Site Down 24h: invalid restore timestamps for %s; reply skipped", incident_id)
            continue
        incident_ref = ref_by_id.get(incident_id) or incident_id
        html = _build_restore_alert_html(
            incident_ref,
            occurred,
            restored,
            row.get("Actual Root Cause") or "",
            row.get("L1 NOC Investigation Result") or "",
            row.get("Resolution") or "",
            row.get("Last Comments") or "",
        )
        ok, reason = _send(html, incident_ref, restore=True)
        if ok:
            ledger.mark_restore_alerted(incident_id)
            sent += 1
            logger.info(f"Site Down 24h: restore-confirmation sent for {incident_id}")
        else:
            logger.error(f"Site Down 24h: restore-confirmation FAILED for {incident_id}: {reason}")
    return sent
