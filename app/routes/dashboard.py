"""Dashboard page routes."""
import csv
import io
import re

from flask import Blueprint, Response, render_template, request

from app.repositories.alarm.alarm_cache_repository import AlarmCacheRepository
from app.repositories.ape_alarm.ape_alarm_cache_repository import ApeAlarmCacheRepository
from app.repositories.incident.incident_status_cache_repository import IncidentStatusCacheRepository
from app.repositories.incwo.incwo_status_cache_repository import IncWoStatusCacheRepository
from app.repositories.site.site_cache_repository import SiteCacheRepository
from app.repositories.vip.vip_alarm_cache_repository import VipAlarmCacheRepository
from app.services.alarm.alarm_service import AlarmService
from app.services.alarm_site_down.alarm_completely_site_down_service import AlarmCompletelySiteDownService
from app.services.alarm_site_down.alarm_site_down_service import AlarmSiteDownService
from app.services.alarm_main_failure.alarm_main_failure_service import AlarmMainFailureService
from app.services.dg_on.dg_on_alarm_service import DgOnAlarmService
from app.services.incident.incident_service import IncidentService
from app.services.incwo.incwo_service import IncWoService
from app.services.mentor.mentor_site_service import MentorSiteService
from app.services.ran.ran_main_ac_alarm_service import RanMainAcAlarmService
from app.services.ran.ran_site_down_service import RanSiteDownService
from app.services.ran.ran_tech_down_service import RanTechDownService
from app.services.vip.vip_alarm_service import VipAlarmService
from app.utils.datetime import format_short_date
from app.utils.logger import get_logger

dashboard_bp = Blueprint("dashboard", __name__)
logger = get_logger(__name__)
alarm_service = AlarmService()
incident_service = IncidentService()
incwo_service = IncWoService()
vip_alarm_service = VipAlarmService()
ran_main_ac_alarm_service = RanMainAcAlarmService()
ran_site_down_service = RanSiteDownService()
ran_tech_down_service = RanTechDownService()
dg_on_alarm_service = DgOnAlarmService()
mentor_site_service = MentorSiteService()
alarm_site_down_service = AlarmSiteDownService()
alarm_completely_site_down_service = AlarmCompletelySiteDownService()
alarm_main_failure_service = AlarmMainFailureService()

_alarm_cache_repository = AlarmCacheRepository()
_incident_status_cache_repository = IncidentStatusCacheRepository()
_incwo_status_cache_repository = IncWoStatusCacheRepository()
_vip_alarm_cache_repository = VipAlarmCacheRepository()
_ape_alarm_cache_repository = ApeAlarmCacheRepository()
_site_cache_repository = SiteCacheRepository()


def _log_dashboard_data_freshness():
    """Logs the last_synced_at of every table the homepage actually reads
    on this view — see logs/dashboard.log (app/utils/logger.py) — so "how
    current was the data a user just saw" is answered directly instead of
    cross-referencing sync_meta against request timing by hand."""
    parts = (
        f"isp_pop={_alarm_cache_repository.last_synced_at('isp_pop_alarm_cache')}, "
        f"incident={_incident_status_cache_repository.last_synced_at('incident_by_status')}, "
        f"incwo={_incwo_status_cache_repository.last_synced_at('inc_wo_by_status')}, "
        f"vip_alarm={_vip_alarm_cache_repository.last_synced_at('vip_alarm')}, "
        f"ape_alarm={_ape_alarm_cache_repository.last_synced_at('ape_alarm')}, "
        f"site={_site_cache_repository.last_synced_at('site_cache')}"
    )
    logger.info(f"Dashboard data as of: {parts}")

# Scopes backed by a real MSSQL query (dashboard.drilldown routes these to
# drilldown/alarms.html + live rows). Every other scope is still a static
# placeholder card, so it falls through to the empty-state template.
_LIVE_ALARM_SCOPES = {
    "ISP POP": alarm_service.get_isp_pop_details,
    "EZE": alarm_service.get_eze_details,
    "TCT Port Down/Up": alarm_service.get_tct_details,
    "IT NODE": alarm_service.get_it_node_details,
}

# Which column set drilldown/alarms.html renders for each scope — each of
# the 4 live scopes has its own shape (POP: Root Cause; EZE: TT/INC-WOID +
# Interface; TCT: Interface + Additional Info, no TT/INC-WOID; IT NODE:
# TT/INC-WOID + Interface + Root Cause + Source Group all together — Device/
# IP/Province just render blank since IT_NODE alarms carry none of that).
_ALARM_SOURCE = {
    "ISP POP": "isp_pop",
    "EZE": "eze",
    "TCT Port Down/Up": "tct",
    "IT NODE": "it_node",
}

_CSV_COLUMNS_BY_SOURCE = {
    "isp_pop": [
        ("pop_name", "POP Name"), ("pop_code", "POP Code"), ("device_name", "Device"),
        ("ip_address", "IP"), ("alarm_name", "Alarm Name"), ("down_time", "Down Time"),
        ("outage_min", "Outage(min)"), ("root_cause", "Root Cause"),
        ("province", "Province"), ("note", "Note"),
    ],
    "eze": [
        ("rtid", "TT/INC-WOID"), ("pop_name", "POP Name"), ("pop_code", "POP Code"),
        ("device_name", "Device"), ("ip_address", "IP"), ("alarm_name", "Alarm Name"),
        ("down_time", "Down Time"), ("outage_min", "Outage(min)"), ("interface", "Interface"),
        ("province", "Province"), ("note", "Note"),
    ],
    "tct": [
        ("pop_name", "POP Name"), ("pop_code", "POP Code"), ("device_name", "Device"),
        ("ip_address", "IP"), ("alarm_name", "Alarm Name"), ("down_time", "Down Time"),
        ("outage_min", "Outage(min)"), ("interface", "Interface"), ("province", "Province"),
        ("additional_info", "Additional Info"), ("note", "Note"),
    ],
    "it_node": [
        ("rtid", "TT/INC-WOID"), ("device_name", "Device"), ("ip_address", "IP"),
        ("alarm_name", "Alarm Name"), ("down_time", "Down Time"), ("outage_min", "Outage(min)"),
        ("interface", "Interface"), ("root_cause", "Root Cause"), ("source_group", "SourceGroup"),
        ("additional_info", "Additional Info"), ("note", "Note"),
    ],
}

_INCIDENT_CSV_COLUMNS = [
    ("incident_id", "Incident ID"), ("incident_status", "Incident Status"),
    ("wo_id", "INC-WO ID"), ("wo_created_at", "INC-WO Created At"),
    ("wo_status", "INC-WO Status"), ("site_name", "Site Name"), ("site_code", "Site Code"),
    ("occurred_at", "Occurred At"), ("outage_min", "Outage(min)"), ("overdue", "Overdue"),
    ("category", "Category"), ("l1_noc_investigation_result", "L1 NOC Investigation Result"),
    ("nms", "NMS"), ("hub_site", "Hub Site"), ("site_grade", "Site Grade"),
    ("province", "Province"), ("district", "District"), ("commune", "Commune"),
]

_INC_WO_CSV_COLUMNS = [
    ("incident_id", "Incident ID"), ("incident_status", "Incident Status"),
    ("wo_id", "INC-WO ID"), ("wo_created_at", "INC-WO Created At"),
    ("wo_status", "INC-WO Status"), ("site_name", "Site Name"), ("site_code", "Site Code"),
    ("overdue", "Overdue"), ("support_level", "Support Level"),
    ("fault_description", "Fault Description"), ("nms", "NMS"), ("hub_site", "Hub Site"),
    ("site_grade", "Site Grade"), ("province", "Province"), ("district", "District"),
    ("commune", "Commune"),
]

_INC_WO_RESOLVED_CSV_COLUMNS = [
    ("incident_id", "Incident ID"), ("incident_status", "Incident Status"),
    ("wo_id", "INC-WO ID"), ("wo_created_at", "INC-WO Created At"),
    ("wo_status", "INC-WO Status"), ("site_name", "Site Name"), ("site_code", "Site Code"),
    ("overdue", "Overdue"), ("support_level", "Support Level"),
    ("fault_description", "Fault Description"), ("nms", "NMS"), ("hub_site", "Hub Site"),
    ("site_grade", "Site Grade"), ("province", "Province"), ("district", "District"),
    ("commune", "Commune"),
]

_VIP_ALARM_CSV_COLUMNS = [
    ("incident_id", "Incident ID"), ("wo_id", "INC-WO ID"), ("wo_created_at", "INC-WO Created At"),
    ("wo_status", "INC-WO Status"), ("resolved_at", "Resolved At"),
    ("site_name", "Site Name"), ("site_code", "Site Code"), ("occurred_at", "Occurred At"),
    ("outage_min", "Outage(min)"), ("event_name", "Event Name"), ("category", "Category"),
    ("nms", "NMS"), ("technology", "Technology"),
    ("hub_site", "Hub Site"), ("site_grade", "Site Grade"), ("province", "Province"),
]

_RAN_MAIN_AC_ALARM_CSV_COLUMNS = [
    ("incident_id", "Incident ID"), ("wo_id", "INC-WO ID"), ("wo_created_at", "INC-WO Created At"),
    ("wo_status", "INC-WO Status"), ("site_name", "Site Name"), ("site_code", "Site Code"),
    ("occurred_at", "Occurred At"), ("outage_min", "Outage(min)"), ("event_name", "Event Name"),
    ("nms", "NMS"), ("hub_site", "Hub Site"), ("site_grade", "Site Grade"),
    ("province", "Province"), ("remark", "Remark"),
]

_RAN_SITE_DOWN_CSV_COLUMNS = [
    ("incident_id", "Incident ID"), ("wo_id", "INC-WO ID"), ("wo_created_at", "INC-WO Created At"),
    ("wo_status", "INC-WO Status"), ("site_name", "Site Name"), ("site_code", "Site Code"),
    ("occurred_at", "Occurred At"), ("outage_min", "Outage(min)"), ("event_name", "Event Name"),
    ("radio_technology", "Technology"), ("nms", "NMS"), ("hub_site", "Hub Site"), ("site_grade", "Site Grade"),
    ("province", "Province"),
]

_RAN_TECH_DOWN_CSV_COLUMNS = [
    ("incident_id", "Incident ID"), ("wo_id", "INC-WO ID"), ("wo_created_at", "INC-WO Created At"),
    ("wo_status", "INC-WO Status"), ("site_name", "Site Name"), ("site_code", "Site Code"),
    ("occurred_at", "Occurred At"), ("outage_min", "Outage(min)"), ("event_name", "Event Name"),
    ("radio_technology", "Technology"), ("nms", "NMS"), ("hub_site", "Hub Site"), ("site_grade", "Site Grade"),
    ("province", "Province"),
]

_DG_ON_ALARM_CSV_COLUMNS = [
    ("incident_id", "Incident ID"), ("wo_id", "INC-WO ID"), ("wo_created_at", "INC-WO Created At"),
    ("wo_status", "INC-WO Status"), ("site_name", "Site Name"), ("site_code", "Site Code"),
    ("occurred_at", "Occurred At"), ("outage_min", "Outage(min)"), ("event_name", "Event Name"),
    ("nms", "NMS"), ("hub_site", "Hub Site"), ("site_grade", "Site Grade"),
    ("province", "Province"),
]

_ALARM_SITE_DOWN_CSV_COLUMNS = [
    ("incident_id", "Incident ID"), ("wo_id", "INC-WO ID"), ("wo_created_at", "INC-WO Created At"),
    ("wo_status", "INC-WO Status"), ("site_name", "Site Name"), ("site_code", "Site Code"),
    ("occurred_at", "Occurred At"), ("outage_min", "Outage(min)"), ("event_name", "Event Name"),
    ("radio_technology", "Technology"), ("nms", "NMS"), ("hub_site", "Hub Site"), ("site_grade", "Site Grade"),
    ("province", "Province"),
]

_ALARM_COMPLETELY_SITE_DOWN_CSV_COLUMNS = [
    ("incident_id", "Incident ID"), ("wo_id", "INC-WO ID"), ("wo_created_at", "INC-WO Created At"),
    ("wo_status", "INC-WO Status"), ("site_name", "Site Name"), ("site_code", "Site Code"),
    ("occurred_at", "Occurred At"), ("outage_min", "Outage(min)"), ("event_name", "Event Name"),
    ("radio_technology", "Technology"), ("nms", "NMS"), ("hub_site", "Hub Site"), ("site_grade", "Site Grade"),
    ("province", "Province"),
]

_ALARM_MAIN_FAILURE_CSV_COLUMNS = [
    ("incident_id", "Incident ID"), ("wo_id", "INC-WO ID"), ("wo_created_at", "INC-WO Created At"),
    ("wo_status", "INC-WO Status"), ("site_name", "Site Name"), ("site_code", "Site Code"),
    ("occurred_at", "Occurred At"), ("outage_min", "Outage(min)"), ("event_name", "Event Name"),
    ("nms", "NMS"), ("hub_site", "Hub Site"), ("site_grade", "Site Grade"),
    ("province", "Province"),
]

_MENTOR_SITE_CSV_COLUMNS = [
    ("incident_id", "Incident ID"), ("wo_id", "INC-WO ID"), ("wo_created_at", "INC-WO Created At"),
    ("wo_status", "INC-WO Status"), ("resolved_at", "Resolved At"), ("site_name", "Site Name"),
    ("site_code", "Site Code"), ("occurred_at", "Occurred At"), ("outage_min", "Outage(min)"),
    ("event_name", "Event Name"), ("category", "Category"), ("nms", "NMS"),
    ("hub_site", "Hub Site"), ("site_grade", "Site Grade"), ("province", "Province"),
]

_INCIDENT_SITE_DOWN_CSV_COLUMNS = [
    ("incident_id", "Incident ID"), ("wo_id", "INC-WO ID"), ("wo_created_at", "INC-WO Created At"),
    ("wo_status", "INC-WO Status"), ("site_name", "Site Name"), ("site_code", "Site Code"),
    ("occurred_at", "Occurred At"), ("outage_min", "Outage(min)"),
    ("l1_noc_investigation_result", "L1 NOC Investigation Result"), ("nms", "NMS"),
    ("hub_site", "Hub Site"), ("site_grade", "Site Grade"),
    ("province", "Province"), ("district", "District"), ("commune", "Commune"),
]

# One entry per non-alarm drilldown scope, shared by drilldown() (renders a
# template) and drilldown_download() (writes a CSV) — used to be a 5-way
# if/elif repeated in both functions; each scope's fetch/template/columns
# now live in exactly one place.
#   fetch                 — alarm_type -> rows
#   none_is_404            — "Incident"/"INC-WO" only: a None result means an
#                             unknown alarm_type, so drilldown() falls through
#                             to the empty state and drilldown_download()
#                             returns 404. The other scopes never return None.
#   extra_template_kwargs  — "INC-WO Site Down" only: adds the export_scope/
#                             export_type the template needs for its own
#                             download link.
_SCOPE_HANDLERS = {
    "Incident": {
        "fetch": lambda alarm_type: incident_service.get_details(alarm_type),
        "template": "drilldown/incidents.html",
        "csv_columns": _INCIDENT_CSV_COLUMNS,
        "none_is_404": True,
    },
    "INC-WO": {
        "fetch": lambda alarm_type: incwo_service.get_details(alarm_type),
        "template": "drilldown/incwo.html",
        "csv_columns": _INC_WO_CSV_COLUMNS,
        "none_is_404": True,
    },
    "INC-WO Site Down": {
        "fetch": lambda alarm_type: incwo_service.get_site_down_details(alarm_type),
        "template": "drilldown/incwo.html",
        "csv_columns": _INC_WO_CSV_COLUMNS,
        "extra_template_kwargs": lambda alarm_type: {
            "export_scope": "INC-WO Site Down", "export_type": alarm_type,
        },
    },
    "INC-WO Resolved": {
        "fetch": lambda alarm_type: incwo_service.get_resolved_details(),
        "template": "drilldown/incwo_resolved.html",
        "csv_columns": _INC_WO_RESOLVED_CSV_COLUMNS,
    },
    "Incident Site Down": {
        "fetch": lambda alarm_type: incident_service.get_incident_site_down_details(alarm_type),
        "template": "drilldown/incident_site_down.html",
        "csv_columns": _INCIDENT_SITE_DOWN_CSV_COLUMNS,
    },
    "VVIP Site": {
        "fetch": lambda alarm_type: vip_alarm_service.get_details(alarm_type),
        "template": "drilldown/vip_alarm.html",
        "csv_columns": _VIP_ALARM_CSV_COLUMNS,
    },
    "RAN Main AC Alarm": {
        "fetch": lambda alarm_type: ran_main_ac_alarm_service.get_details(alarm_type),
        "template": "drilldown/ran_main_ac_alarm.html",
        "csv_columns": _RAN_MAIN_AC_ALARM_CSV_COLUMNS,
    },
    "RAN Site Down": {
        "fetch": lambda alarm_type: ran_site_down_service.get_details(alarm_type),
        "template": "drilldown/ran_site_down.html",
        "csv_columns": _RAN_SITE_DOWN_CSV_COLUMNS,
    },
    "RAN Tech Down": {
        "fetch": lambda alarm_type: ran_tech_down_service.get_details(alarm_type),
        "template": "drilldown/ran_tech_down.html",
        "csv_columns": _RAN_TECH_DOWN_CSV_COLUMNS,
    },
    "Alarm DG On": {
        "fetch": lambda alarm_type: dg_on_alarm_service.get_details(alarm_type),
        "template": "drilldown/dg_on_alarm.html",
        "csv_columns": _DG_ON_ALARM_CSV_COLUMNS,
    },
    "Alarm Site Down": {
        "fetch": lambda alarm_type: alarm_site_down_service.get_details(alarm_type),
        "template": "drilldown/alarm_site_down.html",
        "csv_columns": _ALARM_SITE_DOWN_CSV_COLUMNS,
    },
    "Alarm Completely Site Down": {
        "fetch": lambda alarm_type: alarm_completely_site_down_service.get_details(alarm_type),
        "template": "drilldown/alarm_completely_site_down.html",
        "csv_columns": _ALARM_COMPLETELY_SITE_DOWN_CSV_COLUMNS,
    },
    "Alarm Main Failure": {
        "fetch": lambda alarm_type: alarm_main_failure_service.get_details(alarm_type),
        "template": "drilldown/alarm_main_failure.html",
        "csv_columns": _ALARM_MAIN_FAILURE_CSV_COLUMNS,
    },
    "Mentor sites": {
        "fetch": lambda alarm_type: mentor_site_service.get_alarm_details(
            alarm_type, request.args.get("site_code", "")
        ),
        "template": "drilldown/mentor_site.html",
        "csv_columns": _MENTOR_SITE_CSV_COLUMNS,
    },
    "Mentor Site": {
        "fetch": lambda alarm_type: mentor_site_service.get_alarm_details(
            alarm_type, request.args.get("site_code", "")
        ),
        "template": "drilldown/mentor_site.html",
        "csv_columns": _MENTOR_SITE_CSV_COLUMNS,
    },
}

# Which _SCOPE_HANDLERS-routed scopes get the "Occurred At" date-range
# filter (see drilldown/_date_filter.html) — only scopes whose rows
# actually carry an occurred_at field. "Incident" and "INC-WO Resolved"
# are absent because inc_wo_by_status/inc_wo_resolved have no occurred_at
# (only INC-WO Created At / Resolved At) — ISP POP/EZE/TCT/IT NODE filter
# Down Time instead, via their own separate path (_fetch_rows()).
_DATE_FILTERABLE_SCOPES = {
    "Incident", "Incident Site Down", "VVIP Site", "RAN Main AC Alarm",
    "RAN Site Down", "RAN Tech Down", "Alarm DG On", "Alarm Site Down",
    "Alarm Completely Site Down", "Alarm Main Failure", "Mentor sites", "Mentor Site",
}


def _filter_by_occurred_at(rows, date_from, date_to):
    """Narrows `rows` to those whose occurred_at falls within
    [date_from, date_to] (each 'YYYY-MM-DD', inclusive) — same plain
    string-comparison approach as _fetch_rows()'s down_time filter, since
    occurred_at is also stored as 'YYYY-MM-DD HH:MM:SS' (ISO-sortable)."""
    if date_from:
        rows = [r for r in rows if (r.get("occurred_at") or "")[:10] >= date_from]
    if date_to:
        rows = [r for r in rows if (r.get("occurred_at") or "")[:10] <= date_to]
    return rows


@dashboard_bp.route("/")
def index():
    _log_dashboard_data_freshness()
    return render_template(
        "dashboard/index.html",
        isp_pop_counts=alarm_service.get_isp_pop_counts(),
        eze_counts=alarm_service.get_eze_counts(),
        tct_counts=alarm_service.get_tct_counts(),
        incident_counts=incident_service.get_incident_counts(),
        incwo_counts=incwo_service.get_incwo_counts(),
        vip_site_counts=vip_alarm_service.get_counts(),
        ran_main_ac_alarm_counts=ran_main_ac_alarm_service.get_counts(),
        ran_site_down_counts=ran_site_down_service.get_counts(),
        ran_tech_down_counts=ran_tech_down_service.get_counts(),
        mentor_site_counts=mentor_site_service.get_counts(),
    )


def _fetch_rows(scope, alarm_type, date_from="", date_to=""):
    """Rows for `scope`, optionally narrowed to one badge's alarm type
    (case-insensitive — ISP POP/EZE/TCT each store a different case) and/or
    a Down Time date range. down_time is stored as 'YYYY-MM-DD HH:MM:SS'
    and date_from/date_to arrive as 'YYYY-MM-DD' (straight from an
    <input type="date">) — both are ISO format, so a plain string
    comparison on the first 10 characters sorts correctly without needing
    to parse either side into a real date."""
    fetch_details = _LIVE_ALARM_SCOPES.get(scope)
    if not fetch_details:
        return None
    rows = fetch_details()
    if alarm_type:
        rows = [r for r in rows if (r.get("alarm") or "").strip().upper() == alarm_type.strip().upper()]
    if date_from:
        rows = [r for r in rows if (r.get("down_time") or "")[:10] >= date_from]
    if date_to:
        rows = [r for r in rows if (r.get("down_time") or "")[:10] <= date_to]
    return rows


def _safe_filename(scope, alarm_type):
    """Build the CSV download filename from `scope`/`alarm_type` (query-string
    values) with only [A-Za-z0-9_-] kept, so neither can inject characters
    into the Content-Disposition header."""
    raw = scope + ("_" + alarm_type if alarm_type else "")
    raw = raw.replace("/", "-").replace(" ", "_")
    safe = re.sub(r"[^A-Za-z0-9_-]", "", raw)
    return f"{safe}.csv"


def _date_range_label(date_from, date_to):
    if date_from and date_to:
        return f"{format_short_date(date_from)} - {format_short_date(date_to)}"
    if date_from:
        return f"From {format_short_date(date_from)}"
    if date_to:
        return f"Until {format_short_date(date_to)}"
    return "All Dates"


@dashboard_bp.route("/drilldown")
def drilldown():
    title = request.args.get("title", "Detail")
    label = request.args.get("label", "")
    value = request.args.get("value", "0")
    scope = request.args.get("scope", "this category")
    alarm_type = request.args.get("type", "")
    date_from = request.args.get("from", "")
    date_to = request.args.get("to", "")

    handler = _SCOPE_HANDLERS.get(scope)
    if handler:
        rows = handler["fetch"](alarm_type)
        if rows is not None or not handler.get("none_is_404"):
            extra = handler["extra_template_kwargs"](alarm_type) if "extra_template_kwargs" in handler else {}
            if rows is not None and scope in _DATE_FILTERABLE_SCOPES:
                rows = _filter_by_occurred_at(rows, date_from, date_to)
                extra = {
                    **extra,
                    "date_from": date_from, "date_to": date_to,
                    "date_from_display": format_short_date(date_from),
                    "date_to_display": format_short_date(date_to),
                    "date_range_label": _date_range_label(date_from, date_to),
                }
            return render_template(handler["template"], title=title, label=label, rows=rows, **extra)
        # None + none_is_404 (unknown "Incident"/"INC-WO" alarm_type) falls
        # through to the empty-state template below, same as every other
        # scope with no live backing query.

    rows = _fetch_rows(scope, alarm_type, date_from, date_to)
    if rows is not None:
        return render_template(
            "drilldown/alarms.html", title=title, label=label, scope=scope,
            alarm_type=alarm_type, rows=rows, source=_ALARM_SOURCE[scope],
            date_from=date_from, date_to=date_to,
            date_from_display=format_short_date(date_from),
            date_to_display=format_short_date(date_to),
            date_range_label=_date_range_label(date_from, date_to),
        )

    # Not one of the live scopes above — still a static placeholder card,
    # so this page has no real backing query and renders the empty state.
    return render_template(
        "drilldown/index.html", title=title, label=label, value=value, scope=scope, rows=[]
    )


def _csv_response(rows, columns, filename):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header for _, header in columns)
    for row in rows:
        writer.writerow(row.get(key, "") for key, _ in columns)
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@dashboard_bp.route("/drilldown/download")
def drilldown_download():
    scope = request.args.get("scope", "")
    alarm_type = request.args.get("type", "")
    date_from = request.args.get("from", "")
    date_to = request.args.get("to", "")

    handler = _SCOPE_HANDLERS.get(scope)
    if handler:
        rows = handler["fetch"](alarm_type)
        if rows is None and handler.get("none_is_404"):
            return Response("Unknown or unavailable scope", status=404)
        if rows is not None and scope in _DATE_FILTERABLE_SCOPES:
            rows = _filter_by_occurred_at(rows, date_from, date_to)
        return _csv_response(rows, handler["csv_columns"], _safe_filename(scope, alarm_type))

    rows = _fetch_rows(scope, alarm_type, date_from, date_to)
    if rows is None:
        return Response("Unknown or unavailable scope", status=404)

    columns = _CSV_COLUMNS_BY_SOURCE[_ALARM_SOURCE[scope]]
    return _csv_response(rows, columns, _safe_filename(scope, alarm_type))
