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
from app.repositories.site.site_technology_cache_repository import (
    SiteTechnologyCacheRepository,
)
from app.repositories.vip.vip_site_cache_repository import VipSiteCacheRepository
from app.utils.logger import get_logger
from webhook.common import _id_link, _post_json

logger = get_logger(__name__)

_SITE_DOWN_TABLE = "incident_site_down"
_SITE_TECHNOLOGY_TABLE = "site_technology_cache"
_VIP_SITE_TABLE = "vip_site_cache"

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


def _format_services_impacted(site_code, tech_rows_by_site):
    """'2G/4G', '2G/3G/4G/5G', etc. — fixed generation order, not
    however site_technology_cache happens to list them. Empty string
    (field simply omitted from the message) if this site has no known
    technology inventory at all, rather than a misleading blank line."""
    techs = {t.lower() for t in tech_rows_by_site.get(site_code, [])}
    ordered = [g.upper() for g in _TECH_ORDER if g in techs]
    return "/".join(ordered)


def _format_areas_impacted(sites):
    """'Svay Rieng Pro, Chantrea Dis, Chres Com' for one site, or every
    impacted site's own areas joined with ' | ' for a multi-site
    incident — deduped, so 5 sites sharing the same commune don't repeat
    it 5 times. Matches the user's own real examples' Province/District/
    Commune abbreviation suffixes exactly; any missing part for a given
    site is simply left out of that site's own group, not shown blank."""
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


def _format_vip_impacted(sites, vip_lookup):
    """'SITE_A (1234) - VVIP, SITE_B (5678) - VIP' for every impacted
    site that's actually VIP/VVIP, or '' if none of them are (field
    omitted from the message entirely in that case, same convention as
    Services/Areas Impacted)."""
    parts = []
    for s in sites:
        tier = vip_lookup.get(s.get("site_code"))
        if tier:
            parts.append(f"{s.get('site_name')} ({s.get('site_code')}) - {tier}")
    return ", ".join(dict.fromkeys(parts))


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
        groups[incident_id].append(r)
    return [(incident_id, groups[incident_id]) for incident_id in order]


def _first_nonempty(sites, key):
    """First real (non-blank) value of `key` across every site row in
    the group — NOT just sites[0], which is the exact bug this
    replaces: incident_site_down has one row per (incident, site), and
    a multi-site incident's OTHER fields (wo_id in particular) can be
    set on one site's row and blank on another's. Picking sites[0]
    alone meant a real INC-WO ref sitting on site #2 silently lost to
    an empty value on site #1 (confirmed live: INC-0000262688's own
    7253 row has no wo_id, but its sibling 7252 row has a real one)."""
    for s in sites:
        value = (s.get(key) or "").strip()
        if value:
            return value
    return ""


def _first_row_with(sites, key):
    """Same search as _first_nonempty(), but returns the whole row
    instead of just the value — needed so the Streamline link below can
    read wo_numeric_id off the SAME row its wo_id came from, not an
    unrelated sibling site's row."""
    for s in sites:
        if (s.get(key) or "").strip():
            return s
    return None


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
    """'Site X (1234) down over 24 hrs' for one site; '4 Sites down over
    24hrs hub site DAMBOUK_RUNG (1166,1234)' for a multi-site incident
    that includes a hub (hub(s) called out by name/codes in addition to
    the plain site count); '4 sites down over 24hrs' for a multi-site
    incident with no hub. Each case's own exact wording/spacing matches
    the user's own real examples, not a single unified template."""
    if len(sites) == 1:
        s = sites[0]
        return f"Site {s.get('site_name')} ({s.get('site_code')}) down over 24 hrs"
    hub_groups = _hub_site_groups(sites)
    if not hub_groups:
        return f"{len(sites)} sites down over 24hrs"
    hub_desc = " ".join(f"hub site {name} ({','.join(codes)})" for name, codes in hub_groups)
    return f"{len(sites)} Sites down over 24hrs {hub_desc}"


def _build_down_alert_html(sites, services, areas, vip_impacted=""):
    """`sites` is every site row for ONE incident (1 for a single-site
    incident, more for a multi-site one) — all fields below read off
    sites[0] except the ones that genuinely depend on the whole group
    (site names/codes, Number of Site Impact, services, areas, Source,
    VIP/VVIP Impacted, and the INC-WO ref — see _first_nonempty()'s own
    docstring for why that one specifically can't just use sites[0])."""
    first = sites[0]
    occurred = min((_parse_ts(s.get("occurred_at")) for s in sites if s.get("occurred_at")), default=None)
    site_names = ", ".join(dict.fromkeys(s.get("site_name") for s in sites if s.get("site_name")))
    site_codes = ", ".join(dict.fromkeys(s.get("site_code") for s in sites if s.get("site_code")))

    # Ref text is whichever site's own wo_id is real (see
    # _first_nonempty()'s own docstring); the Streamline LINK has to
    # come from that SAME row's wo_numeric_id, not just any sibling
    # site's, or the link could point at a different work order than
    # the ref text actually names. Falls back to linking the Incident
    # itself (not a WO) when no site in the group has a real wo_id at
    # all — same two-tier link webhook/common.py's own drilldown tables
    # already use for this exact "Incident ID or WO ID" cell.
    wo_row = _first_row_with(sites, "wo_id")
    if wo_row:
        wo_ref = wo_row["wo_id"].strip()
        link = _id_link(wo_row, "wo_id")
    else:
        wo_ref = first.get("incident_id")
        link = _id_link(first, "incident_id")
    ref_display = f'<a href="{link}">{wo_ref}</a>' if link else wo_ref

    items = [
        f"Incident/Work Order Ref: {ref_display}",
        f"Site Name: {site_names or '-'}",
        f"Site Code: {site_codes or '-'}",
        f"Number of Site Impact: {len(sites)}",
    ]
    if services:
        items.append(f"Services Impacted: {services}")
    if areas:
        items.append(f"Areas Impacted: {areas}")
    if vip_impacted:
        items.append(f"VIP/VVIP Impacted: {vip_impacted}")
    source = ", ".join(dict.fromkeys(s.get("source") for s in sites if s.get("source")))
    if source:
        items.append(f"Source: {source}")
    items.append(f"Site Priority: {first.get('site_grade') or '-'}")
    items.append(f"Incident/Outage Start: {_format_display_ts(occurred) if occurred else '-'}")
    root_cause = (first.get("l1_noc_investigation_result") or "").strip()
    items.append(f"Root Cause: {root_cause if root_cause else 'Pending investigation'}")
    note = (first.get("last_comments") or "").strip()
    if note:
        items.append(f"Note: {note}")

    li = "".join(f"<li>{i}</li>" for i in items)
    return (
        f"<b>⚠️ {_build_down_alert_title(sites)}</b><br><br>"
        "Dear All,<br>"
        "Please be informed that the following site has been down for over 24 hours:"
        f"<ul>{li}</ul>"
        "Best Regards,<br>Work Flow Sitedown-alert"
    )


def _build_restore_alert_html(occurred, restored, root_cause, note=""):
    """No bold title line here, deliberately — unlike the down-alert,
    every one of the user's own real restore-confirmation examples
    (Nisen EM's, the Workflows bot's) starts directly with "Dear All,",
    no header. Action Recovery is `note` (last_comments at resolution
    time) — same fallback convention as Root Cause ("Pending
    investigation" when empty) rather than a fixed placeholder, since
    last_comments is where NOC actually records what fixed it."""
    down_hours = (restored - occurred).total_seconds() / 3600 if occurred and restored else None
    items = [
        f"Incident/Outage Start: {_format_display_ts(occurred) if occurred else '-'}",
        f"Restored: {_format_display_ts(restored) if restored else '-'}",
    ]
    if down_hours is not None:
        items.append(f"Outage Duration(DD:HH:MM): {_format_duration_ddhhmm(down_hours)}")
    items.append(f"Root Cause: {root_cause.strip() if root_cause and root_cause.strip() else 'Pending investigation'}")
    items.append(f"Action Recovery: {note.strip() if note and note.strip() else 'Pending investigation'}")

    li = "".join(f"<li>{i}</li>" for i in items)
    return (
        "Dear All,<br>"
        "Please be informed that the incident report above has been restored."
        f"<ul>{li}</ul>"
        "Best Regards,<br>Work Flow Sitedown-alert"
    )


def _send(html, incident_ref, *, restore=False):
    """POSTs {text, incident_ref} to one of two separate Power Automate
    flows/URLs — the down-alert's own flow posts to Teams and saves the
    Message ID into a SharePoint list keyed by incident_ref; the
    restore-confirmation's own SEPARATE flow looks that row up, replies
    in the same thread using it, then deletes the row. Two independent
    flows rather than one flow with a branch (see
    SITE_DOWN_24H_ALERT_RESTORE_WEBHOOK_URL's own config comment for
    why) — `restore` just picks which URL to POST to, nothing else
    differs between the two calls."""
    config_key = (
        "SITE_DOWN_24H_ALERT_RESTORE_WEBHOOK_URL" if restore else "SITE_DOWN_24H_ALERT_WEBHOOK_URL"
    )
    url = current_app.config[config_key]
    if not url:
        return False, "no URL configured"
    payload = {"text": html, "incident_ref": incident_ref}
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
    now = _now_local().replace(tzinfo=None)

    sent = 0
    for incident_id, sites in _group_by_incident(rows):
        occurred = min(
            (_parse_ts(s.get("occurred_at")) for s in sites if s.get("occurred_at")), default=None
        )
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
        incident_ref = _first_nonempty(sites, "wo_id") or incident_id
        ok, reason = _send(html, incident_ref)
        if ok:
            # Multi-site incident -> one ledger row, first site's own
            # code (debugging/lookup convenience only — dedup is keyed
            # by incident_id, not site_code).
            ledger.mark_down_alerted(incident_id, sites[0].get("site_code"), incident_ref)
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

    resolved_rows = IncidentRepository().fetch_site_down_restored_by_ids(pending_ids)
    sent = 0
    for row in resolved_rows:
        incident_id = row.get("Incident ID")
        restored = _parse_ts(row.get("Restored At"))
        if not incident_id or not restored:
            continue
        occurred = occurred_by_id.get(incident_id)
        root_cause = row.get("L1 NOC Investigation Result") or ""
        note = row.get("Last Comments") or ""
        html = _build_restore_alert_html(occurred, restored, root_cause, note)
        incident_ref = ref_by_id.get(incident_id) or incident_id
        ok, reason = _send(html, incident_ref, restore=True)
        if ok:
            ledger.mark_restore_alerted(incident_id)
            sent += 1
            logger.info(f"Site Down 24h: restore-confirmation sent for {incident_id}")
        else:
            logger.error(f"Site Down 24h: restore-confirmation FAILED for {incident_id}: {reason}")
    return sent
