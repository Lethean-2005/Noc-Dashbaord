"""Dashboard page routes."""

import csv
import getpass
import io
import math
import re
from flask import Blueprint, Response, abort, current_app, g, redirect, render_template, request, url_for

from app.repositories.alarm.alarm_cache_repository import AlarmCacheRepository
from app.repositories.ape_alarm.ape_alarm_cache_repository import ApeAlarmCacheRepository
from app.repositories.incident.incident_resolution_time_weekly_cache_repository import (
    IncidentResolutionTimeWeeklyCacheRepository,
)
from app.repositories.incident.incident_response_time_weekly_cache_repository import (
    IncidentResponseTimeWeeklyCacheRepository,
)
from app.repositories.incident.incident_response_time_details_cache_repository import (
    IncidentResponseTimeDetailsCacheRepository,
)
from app.repositories.incident.incident_resolution_time_details_cache_repository import (
    IncidentResolutionTimeDetailsCacheRepository,
)
from app.repositories.incident.incident_sla_compliance_weekly_cache_repository import (
    IncidentSlaComplianceWeeklyCacheRepository,
)
from app.repositories.incident.incident_sla_compliance_details_cache_repository import (
    IncidentSlaComplianceDetailsCacheRepository,
)
from app.repositories.sla_policy.sla_policy_cache_repository import SlaPolicyCacheRepository
from app.repositories.incident.incident_status_cache_repository import IncidentStatusCacheRepository
from app.repositories.incwo.incwo_status_cache_repository import IncWoStatusCacheRepository
from app.repositories.site.site_cache_repository import SiteCacheRepository
from app.repositories.vip.vip_alarm_cache_repository import VipAlarmCacheRepository
from app.services.alarm.alarm_service import AlarmService
from app.services.alarm.alarm_sync_service import AlarmSyncService
from app.services.alarm_site_down.alarm_completely_site_down_service import (
    AlarmCompletelySiteDownService,
)
from app.services.alarm_site_down.alarm_site_down_service import AlarmSiteDownService
from app.services.alarm_main_failure.alarm_main_failure_service import AlarmMainFailureService
from app.services.dg_on.dg_on_alarm_service import DgOnAlarmService
from app.services.incident.incident_service import (
    IncidentService,
    _filter_rows_by_categories,
    _now_local,
    _smooth_path,
)
from app.services.incwo.incwo_service import IncWoService
from app.services.mentor.mentor_site_service import MentorSiteService
from app.services.ran.ran_main_ac_alarm_service import RanMainAcAlarmService
from app.services.ran.ran_site_down_service import RanSiteDownService
from app.services.ran.ran_tech_down_service import RanTechDownService
from app.services.ran.ran_voltage_service import RanVoltageService
from app.services.scheduler_utils import seconds_until_next_aligned_time
from app.services.vip.vip_alarm_service import VipAlarmService
from app.utils.datetime import filter_calendar_dates, format_short_date
from app.utils.logger import get_logger

dashboard_bp = Blueprint("dashboard", __name__)
logger = get_logger(__name__)

# The OS account this Flask process runs as — a suggested (never
# locked) default for the Acknowledge popup's "Your Name" field until a
# browser submits its own value (see acknowledge.js's openAckModal()).
_DEFAULT_ACK_USERNAME = getpass.getuser()
alarm_service = AlarmService()
alarm_sync_service = AlarmSyncService()
incident_service = IncidentService()
incwo_service = IncWoService()

# Shared by every service below that reads ape_alarm/site_cache — each used
# to construct its own repository, so every one of them independently
# re-read the same two tables on every dashboard render (ApeAlarmCacheRepository/
# SiteCacheRepository.fetch_all() are their own 15s ttl_cache, so wiring
# them all to one instance actually dedupes the read instead of just
# moving where it happens).
_shared_ape_alarm_cache_repository = ApeAlarmCacheRepository()
_shared_site_cache_repository = SiteCacheRepository()

vip_alarm_service = VipAlarmService(site_cache_repository=_shared_site_cache_repository)
ran_main_ac_alarm_service = RanMainAcAlarmService(
    ape_alarm_cache_repository=_shared_ape_alarm_cache_repository,
    site_cache_repository=_shared_site_cache_repository,
)
ran_site_down_service = RanSiteDownService(
    ape_alarm_cache_repository=_shared_ape_alarm_cache_repository,
    site_cache_repository=_shared_site_cache_repository,
)
ran_tech_down_service = RanTechDownService(
    ape_alarm_cache_repository=_shared_ape_alarm_cache_repository,
    site_cache_repository=_shared_site_cache_repository,
)
ran_voltage_service = RanVoltageService(
    ape_alarm_cache_repository=_shared_ape_alarm_cache_repository,
    site_cache_repository=_shared_site_cache_repository,
)
dg_on_alarm_service = DgOnAlarmService(
    ape_alarm_cache_repository=_shared_ape_alarm_cache_repository,
    site_cache_repository=_shared_site_cache_repository,
)
mentor_site_service = MentorSiteService(
    ape_alarm_cache_repository=_shared_ape_alarm_cache_repository,
    site_cache_repository=_shared_site_cache_repository,
)
alarm_site_down_service = AlarmSiteDownService(
    ape_alarm_cache_repository=_shared_ape_alarm_cache_repository,
    site_cache_repository=_shared_site_cache_repository,
)
alarm_completely_site_down_service = AlarmCompletelySiteDownService(
    ape_alarm_cache_repository=_shared_ape_alarm_cache_repository,
    site_cache_repository=_shared_site_cache_repository,
)
alarm_main_failure_service = AlarmMainFailureService(
    ape_alarm_cache_repository=_shared_ape_alarm_cache_repository,
    site_cache_repository=_shared_site_cache_repository,
)

_alarm_cache_repository = AlarmCacheRepository()
_incident_status_cache_repository = IncidentStatusCacheRepository()
_incwo_status_cache_repository = IncWoStatusCacheRepository()
_vip_alarm_cache_repository = VipAlarmCacheRepository()
_ape_alarm_cache_repository = ApeAlarmCacheRepository()
_site_cache_repository = SiteCacheRepository()
_response_time_weekly_cache_repository = IncidentResponseTimeWeeklyCacheRepository()
_response_time_details_cache_repository = IncidentResponseTimeDetailsCacheRepository()
_resolution_time_weekly_cache_repository = IncidentResolutionTimeWeeklyCacheRepository()
_resolution_time_details_cache_repository = IncidentResolutionTimeDetailsCacheRepository()
_sla_compliance_weekly_cache_repository = IncidentSlaComplianceWeeklyCacheRepository()
_sla_compliance_details_cache_repository = IncidentSlaComplianceDetailsCacheRepository()

_RESPONSE_TIME_WEEKLY_TABLE = "incident_response_time_weekly"
_RESPONSE_TIME_DETAILS_TABLE = "incident_response_time_details"
_RESOLUTION_TIME_WEEKLY_TABLE = "incident_resolution_time_weekly"
_RESOLUTION_TIME_DETAILS_TABLE = "incident_resolution_time_details"

# One shared column set per details table, used by BOTH
# _response_time_duration_by_week()/_resolution_time_duration_by_week()
# and _response_time_extreme_incident_by_week()/_resolution_time_
# extreme_incident_by_week() — these used to each request their own
# narrower/wider subset, which gave _cached_fetch_columns() a different
# cache key per caller and silently read the SAME ~7-14k row table
# twice per page load instead of once (confirmed live via cProfile:
# 4 real fetch_columns() DB reads per request where only 2 should ever
# be needed). Same superset for both callers means one fetch, shared.
_RESPONSE_TIME_DETAIL_COLUMNS = ("incident_id", "category", "iso_week", "occurred_at", "response_minutes")
_RESOLUTION_TIME_DETAIL_COLUMNS = ("incident_id", "category", "iso_week", "occurred_at", "resolution_minutes")
_SLA_COMPLIANCE_WEEKLY_TABLE = "incident_sla_compliance_weekly"
_SLA_COMPLIANCE_DETAILS_TABLE = "incident_sla_compliance_details"
_sla_policy_cache_repository = SlaPolicyCacheRepository()
_SLA_POLICY_TABLE = "sla_policy"


def _log_dashboard_data_freshness():
    """Logs the last_synced_at of every table the homepage reads, to
    logs/dashboard.log — answers "how current was the data a user just
    saw" directly."""
    parts = (
        f"isp_pop={_alarm_cache_repository.last_synced_at('isp_pop_alarm_cache')}, "
        f"incident={_incident_status_cache_repository.last_synced_at('incident_by_status')}, "
        f"incwo={_incwo_status_cache_repository.last_synced_at('inc_wo_by_status')}, "
        f"vip_alarm={_vip_alarm_cache_repository.last_synced_at('vip_alarm')}, "
        f"ape_alarm={_ape_alarm_cache_repository.last_synced_at('ape_alarm')}, "
        f"site={_site_cache_repository.last_synced_at('site_cache')}"
    )
    logger.info(f"Dashboard data as of: {parts}")


def _log_dashboard_refresh():
    """Logs a bare 'Dashboard Refresh' line to logs/dashboard.log, one
    per clock-aligned tick matching the browser's own auto-reload
    cadence."""
    logger.info("Dashboard Refresh")


def start(app, interval_seconds=None):
    """Background heartbeat for logs/dashboard.log — logs 'Dashboard
    Refresh' on its own clock-aligned schedule so the log has a regular
    trace even with no page views. index()'s own freshness log still
    fires separately per visit."""
    from app.services.scheduler_utils import seconds_until_next_aligned_time, start_singleton_loop

    wait = interval_seconds or app.config["DASHBOARD_LOG_INTERVAL_SECONDS"]
    tz_name = app.config["TIMEZONE"]
    delay = seconds_until_next_aligned_time(wait, tz_name, offset_seconds=95)
    start_singleton_loop(
        app,
        _log_dashboard_refresh,
        wait,
        thread_name="dashboard-freshness-log",
        log_message=f"Dashboard freshness heartbeat started (every {wait}s, "
        f"first run in {delay:.0f}s)",
        first_run_delay=delay,
        next_delay_fn=lambda: seconds_until_next_aligned_time(wait, tz_name, offset_seconds=95),
    )


# Scopes backed by a real MSSQL query, routed to drilldown/alarms.html.
# Every other live scope is handled by _SCOPE_HANDLERS below; a scope in
# neither dict falls through to the empty-state template.
_LIVE_ALARM_SCOPES = {
    "ISP POP": alarm_service.get_isp_pop_details,
    "EZE": alarm_service.get_eze_details,
    "IP Telcotech/Cellcard": alarm_service.get_tct_details,
    "IT NODE": alarm_service.get_it_node_details,
    # "Congestion History" is NOT here — _fetch_rows() always resolves it
    # via get_congestion_device_interface_summary() or
    # get_congestion_week_interface_summary() instead (see that
    # function's own docstring); it never falls through to this dict.
}

# Which column set drilldown/alarms.html renders for each scope — each
# of the 4 live scopes has its own shape.
_ALARM_SOURCE = {
    "ISP POP": "isp_pop",
    "EZE": "eze",
    "IP Telcotech/Cellcard": "tct",
    "IT NODE": "it_node",
    "Congestion History": "congestion_history",
}

# The device-click drilldown's own column set (one row per Interface,
# see AlarmService.get_congestion_device_interface_summary()) — a
# different shape than _CSV_COLUMNS_BY_SOURCE["congestion_history"]
# below, which is still the per-alarm-event shape used by the card's
# "Wk 37 · Wk 38 · ..." (all-devices, by week) drilldown.
_CONGESTION_INTERFACE_SUMMARY_CSV_COLUMNS = [
    ("pop_name", "POP Name"),
    ("pop_code", "POP Code"),
    ("pro_owner", "Owner"),
    ("device_name", "Device"),
    ("ip_address", "IP"),
    ("interface", "Interface"),
    ("province", "Province"),
    ("additional_info", "Additional Info"),
    ("latest_occurred_at", "Latest Occurrence"),
    ("total_count", "Total"),
]

_CSV_COLUMNS_BY_SOURCE = {
    "isp_pop": [
        ("rtid", "TT/INC-WOID"),
        ("pop_name", "POP Name"),
        ("pop_code", "POP Code"),
        ("pro_owner", "Owner"),
        ("device_name", "Device"),
        ("ip_address", "IP"),
        ("alarm_name", "Alarm Name"),
        ("down_time", "Down Time"),
        ("outage_min", "Outage(min)"),
        ("interface", "Interface"),
        ("root_cause", "Root Cause"),
        ("province", "Province"),
        ("note", "Note"),
    ],
    "eze": [
        ("rtid", "TT/INC-WOID"),
        ("pop_name", "POP Name"),
        ("pop_code", "POP Code"),
        ("pro_owner", "Owner"),
        ("device_name", "Device"),
        ("ip_address", "IP"),
        ("alarm_name", "Alarm Name"),
        ("down_time", "Down Time"),
        ("outage_min", "Outage(min)"),
        ("interface", "Interface"),
        ("province", "Province"),
        ("note", "Note"),
    ],
    "tct": [
        ("pop_name", "POP Name"),
        ("pop_code", "POP Code"),
        ("pro_owner", "Owner"),
        ("device_name", "Device"),
        ("ip_address", "IP"),
        ("alarm_name", "Alarm Name"),
        ("down_time", "Down Time"),
        ("outage_min", "Outage(min)"),
        ("interface", "Interface"),
        ("province", "Province"),
        ("additional_info", "Additional Info"),
        ("note", "Note"),
    ],
    "congestion_history": [
        ("alarm", "Alarm Type"),
        ("pop_name", "POP Name"),
        ("pop_code", "POP Code"),
        ("pro_owner", "Owner"),
        ("device_name", "Device"),
        ("ip_address", "IP"),
        ("alarm_name", "Alarm Name"),
        ("down_time", "Down Time"),
        ("restored_time", "Restored Time"),
        ("outage_min", "Outage(min)"),
        ("interface", "Interface"),
        ("province", "Province"),
        ("additional_info", "Additional Info"),
        ("note", "Note"),
        ("total_count", "Total"),
    ],
    "it_node": [
        ("rtid", "TT/INC-WOID"),
        ("device_name", "Device"),
        ("ip_address", "IP"),
        ("alarm_name", "Alarm Name"),
        ("down_time", "Down Time"),
        ("outage_min", "Outage(min)"),
        ("interface", "Interface"),
        ("root_cause", "Root Cause"),
        ("source_group", "SourceGroup"),
        ("additional_info", "Additional Info"),
        ("note", "Note"),
    ],
}

_INCIDENT_CSV_COLUMNS = [
    ("incident_id", "Incident ID"),
    ("incident_status", "Incident Status"),
    ("wo_id", "INC-WO ID"),
    ("wo_created_at", "INC-WO Created At"),
    ("wo_status", "INC-WO Status"),
    ("resolved_at", "Resolved At"),
    ("site_name", "Site Name"),
    ("site_code", "Site Code"),
    ("occurred_at", "Occurred At"),
    ("outage_min", "Outage(min)"),
    ("overdue", "Overdue"),
    ("category", "Category"),
    ("responsible_team", "Responsible Team"),
    ("support_level", "Support Level"),
    ("l1_noc_investigation_result", "L1 NOC Investigation Result"),
    ("nms", "NMS"),
    ("hub_site", "Hub Site"),
    ("site_grade", "Site Grade"),
    ("province", "Province"),
    ("district", "District"),
    ("commune", "Commune"),
]

_INCIDENT_CLOSED_TREND_CSV_COLUMNS = [
    ("incident_id", "Incident ID"),
    ("incident_status", "Incident Status"),
    ("closed_at", "Closed At"),
    ("category", "Category"),
    ("site_name", "Site Name"),
    ("site_code", "Site Code"),
    ("province", "Province"),
    ("district", "District"),
    ("commune", "Commune"),
]

_INCIDENT_CREATED_TREND_CSV_COLUMNS = [
    ("incident_id", "Incident ID"),
    ("incident_status", "Incident Status"),
    ("created_at", "Created At"),
    ("category", "Category"),
    ("severity", "Severity"),
    ("site_name", "Site Name"),
    ("site_code", "Site Code"),
    ("vendor", "Vendor"),
    ("province", "Province"),
    ("district", "District"),
    ("commune", "Commune"),
]

_SITE_DOWN_DURATION_CSV_COLUMNS = [
    ("incident_id", "Incident ID"),
    ("site", "Site Name"),
    ("site_code", "Site Code"),
    ("duration_display", "Duration"),
    ("occurred_at", "Occurred At"),
    ("resolved_at", "Resolved At"),
    ("closed_at", "Closed At"),
    ("root_cause_category", "Root Cause Category"),
]

_RESPONSE_TIME_DURATION_CSV_COLUMNS = [
    ("incident_id", "Incident ID"),
    ("category", "Category"),
    ("iso_week", "Week"),
    ("response_display", "Response Time"),
    ("creation_method", "Creation Method"),
    ("occurred_at", "Occurred At"),
    ("took_in_progress_at", "Took In Progress At"),
]

_RESOLUTION_TIME_DURATION_CSV_COLUMNS = [
    ("incident_id", "Incident ID"),
    ("category", "Category"),
    ("iso_week", "Week"),
    ("resolution_display", "Resolution Time"),
    ("creation_method", "Creation Method"),
    ("occurred_at", "Occurred At"),
    ("resolved_at", "Resolved At"),
]

_SLA_COMPLIANCE_DETAILS_CSV_COLUMNS = [
    ("incident_id", "Incident ID"),
    ("category", "Category"),
    ("root_cause_category", "Root Cause Category"),
    ("sla_target_display", "SLA"),
    ("priority", "Priority"),
    ("support_level", "Support Level"),
    ("site_grade", "Site Grade"),
    ("iso_week", "Week"),
    ("occurred_at", "Occurred At"),
    ("response_sla_display", "Response SLA"),
    ("resolution_sla_display", "Resolution SLA"),
]

_INC_WO_CSV_COLUMNS = [
    ("incident_id", "Incident ID"),
    ("incident_status", "Incident Status"),
    ("incident_category", "Incident Category"),
    ("wo_id", "INC-WO ID"),
    ("wo_created_at", "INC-WO Created At"),
    ("wo_status", "INC-WO Status"),
    ("resolved_at", "Resolved At"),
    ("site_name", "Site Name"),
    ("site_code", "Site Code"),
    ("overdue", "Overdue"),
    ("support_level", "Support Level"),
    ("responsible_team", "Responsible Team"),
    ("fault_description", "Fault Description"),
    ("resolution", "Resolution"),
    ("nms", "NMS"),
    ("hub_site", "Hub Site"),
    ("site_grade", "Site Grade"),
    ("province", "Province"),
    ("district", "District"),
    ("commune", "Commune"),
]

_INC_WO_RESOLVED_CSV_COLUMNS = [
    ("incident_id", "Incident ID"),
    ("incident_status", "Incident Status"),
    ("wo_id", "INC-WO ID"),
    ("wo_created_at", "INC-WO Created At"),
    ("wo_status", "INC-WO Status"),
    ("resolved_at", "Resolved At"),
    ("site_name", "Site Name"),
    ("site_code", "Site Code"),
    ("overdue", "Overdue"),
    ("support_level", "Support Level"),
    ("responsible_team", "Responsible Team"),
    ("fault_description", "Fault Description"),
    ("resolution", "Resolution"),
    ("nms", "NMS"),
    ("hub_site", "Hub Site"),
    ("site_grade", "Site Grade"),
    ("province", "Province"),
    ("district", "District"),
    ("commune", "Commune"),
]

_VIP_ALARM_CSV_COLUMNS = [
    ("incident_id", "Incident ID"),
    ("wo_id", "INC-WO ID"),
    ("wo_created_at", "INC-WO Created At"),
    ("wo_status", "INC-WO Status"),
    ("resolved_at", "Resolved At"),
    ("site_name", "Site Name"),
    ("site_code", "Site Code"),
    ("occurred_at", "Occurred At"),
    ("outage_min", "Outage(min)"),
    ("alarm_numeric_id", "ID"),
    ("event_name", "Event Name"),
    ("category", "Category"),
    ("responsible_team", "Responsible Team"),
    ("support_level", "Support Level"),
    ("nms", "NMS"),
    ("technology", "Technology"),
    ("hub_site", "Hub Site"),
    ("site_grade", "Site Grade"),
    ("province", "Province"),
]

_RAN_MAIN_AC_ALARM_CSV_COLUMNS = [
    ("incident_id", "Incident ID"),
    ("wo_id", "INC-WO ID"),
    ("wo_created_at", "INC-WO Created At"),
    ("wo_status", "INC-WO Status"),
    ("site_name", "Site Name"),
    ("site_code", "Site Code"),
    ("occurred_at", "Occurred At"),
    ("outage_min", "Outage(min)"),
    ("alarm_numeric_id", "ID"),
    ("event_name", "Event Name"),
    ("nms", "NMS"),
    ("hub_site", "Hub Site"),
    ("site_grade", "Site Grade"),
    ("province", "Province"),
    ("remark", "Incident Category"),
]

_RAN_SITE_DOWN_CSV_COLUMNS = [
    ("incident_id", "Incident ID"),
    ("wo_id", "INC-WO ID"),
    ("wo_created_at", "INC-WO Created At"),
    ("wo_status", "INC-WO Status"),
    ("site_name", "Site Name"),
    ("site_code", "Site Code"),
    ("occurred_at", "Occurred At"),
    ("outage_min", "Outage(min)"),
    ("alarm_numeric_id", "ID"),
    ("event_name", "Event Name"),
    ("radio_technology", "Technology"),
    ("nms", "NMS"),
    ("hub_site", "Hub Site"),
    ("site_grade", "Site Grade"),
    ("province", "Province"),
]

_RAN_TECH_DOWN_CSV_COLUMNS = [
    ("incident_id", "Incident ID"),
    ("wo_id", "INC-WO ID"),
    ("wo_created_at", "INC-WO Created At"),
    ("wo_status", "INC-WO Status"),
    ("site_name", "Site Name"),
    ("site_code", "Site Code"),
    ("occurred_at", "Occurred At"),
    ("outage_min", "Outage(min)"),
    ("alarm_numeric_id", "ID"),
    ("event_name", "Event Name"),
    ("radio_technology", "Technology"),
    ("nms", "NMS"),
    ("hub_site", "Hub Site"),
    ("site_grade", "Site Grade"),
    ("province", "Province"),
]

_RAN_VOLTAGE_CSV_COLUMNS = [
    ("incident_id", "Incident ID"),
    ("wo_id", "INC-WO ID"),
    ("wo_created_at", "INC-WO Created At"),
    ("wo_status", "INC-WO Status"),
    ("site_name", "Site Name"),
    ("site_code", "Site Code"),
    ("occurred_at", "Occurred At"),
    ("outage_min", "Outage(min)"),
    ("alarm_numeric_id", "ID"),
    ("event_name", "Event Name"),
    ("nms", "NMS"),
    ("hub_site", "Hub Site"),
    ("site_grade", "Site Grade"),
    ("province", "Province"),
    ("remark", "Incident Category"),
]

_DG_ON_ALARM_CSV_COLUMNS = [
    ("incident_id", "Incident ID"),
    ("wo_id", "INC-WO ID"),
    ("wo_created_at", "INC-WO Created At"),
    ("wo_status", "INC-WO Status"),
    ("site_name", "Site Name"),
    ("site_code", "Site Code"),
    ("occurred_at", "Occurred At"),
    ("outage_min", "Outage(min)"),
    ("alarm_numeric_id", "ID"),
    ("event_name", "Event Name"),
    ("nms", "NMS"),
    ("hub_site", "Hub Site"),
    ("site_grade", "Site Grade"),
    ("province", "Province"),
]

_ALARM_SITE_DOWN_CSV_COLUMNS = [
    ("incident_id", "Incident ID"),
    ("wo_id", "INC-WO ID"),
    ("wo_created_at", "INC-WO Created At"),
    ("wo_status", "INC-WO Status"),
    ("site_name", "Site Name"),
    ("site_code", "Site Code"),
    ("occurred_at", "Occurred At"),
    ("outage_min", "Outage(min)"),
    ("alarm_numeric_id", "ID"),
    ("event_name", "Event Name"),
    ("radio_technology", "Technology"),
    ("nms", "NMS"),
    ("hub_site", "Hub Site"),
    ("site_grade", "Site Grade"),
    ("province", "Province"),
]

_ALARM_COMPLETELY_SITE_DOWN_CSV_COLUMNS = [
    ("incident_id", "Incident ID"),
    ("wo_id", "INC-WO ID"),
    ("wo_created_at", "INC-WO Created At"),
    ("wo_status", "INC-WO Status"),
    ("site_name", "Site Name"),
    ("site_code", "Site Code"),
    ("occurred_at", "Occurred At"),
    ("outage_min", "Outage(min)"),
    ("alarm_numeric_id", "ID"),
    ("event_name", "Event Name"),
    ("radio_technology", "Technology"),
    ("nms", "NMS"),
    ("hub_site", "Hub Site"),
    ("site_grade", "Site Grade"),
    ("province", "Province"),
]

_ALARM_MAIN_FAILURE_CSV_COLUMNS = [
    ("incident_id", "Incident ID"),
    ("wo_id", "INC-WO ID"),
    ("wo_created_at", "INC-WO Created At"),
    ("wo_status", "INC-WO Status"),
    ("site_name", "Site Name"),
    ("site_code", "Site Code"),
    ("occurred_at", "Occurred At"),
    ("outage_min", "Outage(min)"),
    ("alarm_numeric_id", "ID"),
    ("event_name", "Event Name"),
    ("nms", "NMS"),
    ("hub_site", "Hub Site"),
    ("site_grade", "Site Grade"),
    ("province", "Province"),
]

_MENTOR_SITE_CSV_COLUMNS = [
    ("incident_id", "Incident ID"),
    ("wo_id", "INC-WO ID"),
    ("wo_created_at", "INC-WO Created At"),
    ("wo_status", "INC-WO Status"),
    ("resolved_at", "Resolved At"),
    ("site_name", "Site Name"),
    ("site_code", "Site Code"),
    ("occurred_at", "Occurred At"),
    ("outage_min", "Outage(min)"),
    ("alarm_numeric_id", "ID"),
    ("event_name", "Event Name"),
    ("category", "Category"),
    ("responsible_team", "Responsible Team"),
    ("support_level", "Support Level"),
    ("nms", "NMS"),
    ("hub_site", "Hub Site"),
    ("site_grade", "Site Grade"),
    ("province", "Province"),
]

_INCIDENT_SITE_DOWN_CSV_COLUMNS = [
    ("incident_id", "Incident ID"),
    ("wo_id", "INC-WO ID"),
    ("wo_created_at", "INC-WO Created At"),
    ("wo_status", "INC-WO Status"),
    ("site_name", "Site Name"),
    ("site_code", "Site Code"),
    ("occurred_at", "Occurred At"),
    ("outage_min", "Outage(min)"),
    ("l1_noc_investigation_result", "L1 NOC Investigation Result"),
    ("nms", "NMS"),
    ("hub_site", "Hub Site"),
    ("site_grade", "Site Grade"),
    ("province", "Province"),
    ("district", "District"),
    ("commune", "Commune"),
]

# One entry per non-alarm drilldown scope, shared by drilldown() (renders
# a template) and drilldown_download() (writes a CSV) — each scope's
# fetch/template/columns live in exactly one place.
#   fetch                  — alarm_type -> rows
#   none_is_404            — a None result means an unknown alarm_type:
#                             drilldown() falls through to the empty
#                             state, drilldown_download() returns 404.
#   extra_template_kwargs  — "INC-WO Site Down" only: adds the
#                             export_scope/export_type its download link needs.
_SCOPE_HANDLERS = {
    "INC-WO All Resolved": {
        "fetch": lambda alarm_type: incwo_service.get_all_resolved_details(),
        "template": "drilldown/incwo_all_resolved.html",
        "csv_columns": [("incident_id", "Incident ID"), ("incident_status", "Incident Status"),
                        ("incident_category", "Category"), ("site_code", "Site Codes"),
                        ("occurred_at", "Occurred At"), ("wo_count", "Total WOs"),
                        ("resolved_wo_count", "Resolved WOs"), ("resolved_at", "Latest WO Resolved At")],
        "none_is_404": False,
    },
    "Incident": {
        "fetch": lambda alarm_type: incident_service.get_details(alarm_type),
        "template": "drilldown/incidents.html",
        "csv_columns": _INCIDENT_CSV_COLUMNS,
        "none_is_404": True,
    },
    "Incident Volume": {
        "fetch": lambda alarm_type: incident_service.get_volume_trend_details(
            alarm_type,
            request.args.getlist("category"),
            request.args.getlist("severity"),
            request.args.getlist("province"),
            request.args.getlist("vendor"),
        ),
        "template": "drilldown/incident_created_trend.html",
        "csv_columns": _INCIDENT_CREATED_TREND_CSV_COLUMNS,
        "none_is_404": True,
        "extra_template_kwargs": lambda alarm_type: {
            "available_categories": incident_service.get_volume_trend_categories(),
            "selected_categories": request.args.getlist("category"),
            "available_severities": incident_service.get_volume_trend_field_values("severity"),
            "selected_severities": request.args.getlist("severity"),
            "available_provinces": incident_service.get_volume_trend_field_values("province"),
            "selected_provinces": request.args.getlist("province"),
            "available_vendors": incident_service.get_volume_trend_field_values("vendor"),
            "selected_vendors": request.args.getlist("vendor"),
        },
    },
    "Incidents Closed": {
        "fetch": lambda alarm_type: incident_service.get_closed_trend_details(
            alarm_type, request.args.getlist("category")
        ),
        "template": "drilldown/incident_closed_trend.html",
        "csv_columns": _INCIDENT_CLOSED_TREND_CSV_COLUMNS,
        "none_is_404": True,
        "extra_template_kwargs": lambda alarm_type: {
            "available_categories": incident_service.get_closed_trend_categories(),
            "selected_categories": request.args.getlist("category"),
        },
    },
    "Site-Down Duration": {
        "fetch": lambda alarm_type: incident_service.get_site_down_duration_details(alarm_type),
        "template": "drilldown/site_down_duration.html",
        "csv_columns": _SITE_DOWN_DURATION_CSV_COLUMNS,
        "none_is_404": True,
        "extra_template_kwargs": lambda alarm_type: {
            "week_options": incident_service.get_site_down_duration_week_options(alarm_type),
        },
    },
    "Top Site Down": {
        "fetch": lambda alarm_type: incident_service.get_top_site_down_details(
            alarm_type, weeks=request.args.getlist("top_site_down_week")
        ),
        "template": "drilldown/top_site_down.html",
        "csv_columns": _SITE_DOWN_DURATION_CSV_COLUMNS,
        "none_is_404": True,
    },
    # Same 30-day Site Down population and row shape as "Top Site Down"
    # above (incident_site_down_duration_weekly, enriched the same way
    # via IncidentService._with_duration_display_and_root_cause()) —
    # reuses that scope's own template/CSV columns rather than a near-
    # duplicate, just grouped by root cause instead of by site. badge_type
    # here is a Root Cause Category name (e.g. "MW transmission
    # failure"), not a site_code/week token.
    "Root Cause Breakdown": {
        "fetch": lambda alarm_type: incident_service.get_site_down_root_cause_details(
            alarm_type,
            site_code=request.args.get("root_cause_site") or None,
            weeks=request.args.getlist("top_site_down_week"),
        ),
        "template": "drilldown/top_site_down.html",
        "csv_columns": _SITE_DOWN_DURATION_CSV_COLUMNS,
        "none_is_404": True,
    },
    # One duration-bucket cell inside a category's expanded panel in the
    # Root Cause Breakdown table (same accordion UI as Incident Volume's
    # own per-category duration breakdown) — badge_type is a duration
    # bucket token (e.g. "lt15m"), `category` a separate query param
    # since every category's bucket cells share the same badge_type.
    "Root Cause Breakdown Duration": {
        "fetch": lambda alarm_type: incident_service.get_site_down_root_cause_duration_details(
            alarm_type,
            category=request.args.get("category"),
            site_code=request.args.get("root_cause_site") or None,
            weeks=request.args.getlist("top_site_down_week"),
        ),
        "template": "drilldown/top_site_down.html",
        "csv_columns": _SITE_DOWN_DURATION_CSV_COLUMNS,
        "none_is_404": True,
    },
    # "Site-Down Root Cause — Breakdown" (the OTHER donut) — same shape
    # as the two handlers above, scoped to "Site-Down Duration — Weekly
    # Trend"'s own Compare Weeks selection instead of 30 days/
    # top-10-sites (see IncidentService.get_site_down_root_cause_week_
    # breakdown()'s own docstring).
    "Site-Down Root Cause Week": {
        "fetch": lambda alarm_type: incident_service.get_site_down_root_cause_week_details(
            alarm_type,
            duration_bucket=request.args.get("root_cause_bucket") or None,
            weeks=request.args.getlist("site_down_duration_week"),
        ),
        "template": "drilldown/top_site_down.html",
        "csv_columns": _SITE_DOWN_DURATION_CSV_COLUMNS,
        "none_is_404": True,
    },
    "Site-Down Root Cause Week Duration": {
        "fetch": lambda alarm_type: incident_service.get_site_down_root_cause_week_duration_details(
            alarm_type,
            category=request.args.get("category"),
            weeks=request.args.getlist("site_down_duration_week"),
        ),
        "template": "drilldown/top_site_down.html",
        "csv_columns": _SITE_DOWN_DURATION_CSV_COLUMNS,
        "none_is_404": True,
    },
    "Response Time Duration": {
        "fetch": lambda alarm_type: _response_time_duration_details(
            alarm_type, request.args.getlist("category")
        ),
        "template": "drilldown/response_time_duration.html",
        "csv_columns": _RESPONSE_TIME_DURATION_CSV_COLUMNS,
        "none_is_404": True,
        "extra_template_kwargs": lambda alarm_type: _response_time_duration_extra_kwargs(alarm_type),
    },
    "Resolution Time Duration": {
        "fetch": lambda alarm_type: _resolution_time_duration_details(
            alarm_type, request.args.getlist("category")
        ),
        "template": "drilldown/resolution_time_duration.html",
        "csv_columns": _RESOLUTION_TIME_DURATION_CSV_COLUMNS,
        "none_is_404": True,
        "extra_template_kwargs": lambda alarm_type: _resolution_time_duration_extra_kwargs(alarm_type),
    },
    # A duration-bucket cell in the "By Category — <Weekday>" popup's
    # breakdown, any category (graph_cards.html) — reuses "Site-Down
    # Duration"'s own template/CSV columns (identical row shape) but its
    # own fetch, since this one matches occurred_at's exact created date
    # rather than "Site-Down Duration"'s closed_at-week badge_type, and
    # also needs `category` (every category's cells share the same
    # badge_type shape) to tell two categories' same-bucket-same-day
    # cells apart.
    "Incident Volume Duration": {
        "fetch": lambda alarm_type: incident_service.get_incident_volume_day_duration_details(
            alarm_type, request.args.getlist("category")
        ),
        "template": "drilldown/site_down_duration.html",
        "csv_columns": _SITE_DOWN_DURATION_CSV_COLUMNS,
        "none_is_404": True,
    },
    "INC-WO": {
        "fetch": lambda alarm_type: incwo_service.get_details(alarm_type),
        "template": "drilldown/incwo.html",
        "csv_columns": _INC_WO_CSV_COLUMNS,
        "none_is_404": True,
        # HTML render only, not CSV export — the unfiltered "View
        # INC-WO" link was rendering every non-closed row as one giant table.
        "row_cap": 500,
    },
    "INC-WO Site Down": {
        "fetch": lambda alarm_type: incwo_service.get_site_down_details(alarm_type),
        "template": "drilldown/incwo.html",
        "csv_columns": _INC_WO_CSV_COLUMNS,
        "extra_template_kwargs": lambda alarm_type: {
            "export_scope": "INC-WO Site Down",
            "export_type": alarm_type,
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
    "DC Low/High": {
        "fetch": lambda alarm_type: ran_voltage_service.get_details(alarm_type),
        "template": "drilldown/ran_voltage.html",
        "csv_columns": _RAN_VOLTAGE_CSV_COLUMNS,
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
    "SLA Compliance": {
        "fetch": lambda alarm_type: _sla_compliance_details(alarm_type),
        "template": "drilldown/sla_compliance_details.html",
        "csv_columns": _SLA_COMPLIANCE_DETAILS_CSV_COLUMNS,
        "none_is_404": True,
    },
}

# Which _SCOPE_HANDLERS-routed scopes get the "Occurred At" date-range
# filter — only scopes whose rows carry an occurred_at field. "INC-WO"
# and "INC-WO Site Down" get their own wo_created_at filter below
# instead (see _WO_CREATED_AT_FILTERABLE_SCOPES); ISP POP/EZE/TCT/IT
# NODE filter Down Time via their own path (_fetch_rows()).
_DATE_FILTERABLE_SCOPES = {
    "Incident",
    "Incident Site Down",
    "VVIP Site",
    "RAN Main AC Alarm",
    "RAN Site Down",
    "RAN Tech Down",
    "DC Low/High",
    "Alarm DG On",
    "Alarm Site Down",
    "Alarm Completely Site Down",
    "Alarm Main Failure",
    "Mentor sites",
    "Mentor Site",
}

# Both scopes render drilldown/incwo.html, whose rows carry wo_created_at
# but no occurred_at — see drilldown/incwo.html's date-filter include.
_WO_CREATED_AT_FILTERABLE_SCOPES = {"INC-WO", "INC-WO Site Down"}


def _filter_by_occurred_at(rows, date_from, date_to):
    """Include complete selected Cambodia days for incident rows."""
    return filter_calendar_dates(rows, "occurred_at", date_from, date_to)


def _filter_by_wo_created_at(rows, date_from, date_to):
    """Include complete selected Cambodia days for work orders."""
    return filter_calendar_dates(rows, "wo_created_at", date_from, date_to)


def _format_minutes(minutes):
    """0.0656 -> '3.9s', 43.8 -> '43.8m', 1028.8 -> '17h 9m'. None -> '--'.

    Sub-minute values keep 1 decimal place rather than rounding to a
    whole second — whole seconds made the Week-over-Week % delta (computed
    from the exact, unrounded minute values) look wrong next to the
    displayed numbers, e.g. "4s -> 3s" reading as 25% next to an actual
    (and correctly shown) 19%, when the real values were 3.9s -> 3.2s."""
    if minutes is None:
        return "--"
    minutes = float(minutes)
    if minutes < 1:
        return f"{minutes * 60:.1f}s"
    if minutes < 60:
        return f"{minutes:.1f}m"
    hours, mins = divmod(round(minutes), 60)
    return f"{hours}h {mins}m"


def _weekly_time_pct_delta(last_week_value, this_week_value):
    """Returns (pct, improved) — pct is the absolute % change rounded to
    an int and capped at 100, improved is True when this week's value
    is lower (faster is always the improvement for both these cards).
    None if last_week_value is missing/zero (can't compute a % change
    against it). Capped rather than shown raw because a tiny baseline
    (e.g. a single near-instant auto-acknowledged incident's response
    time) can otherwise blow the % change up into the thousands for a
    small absolute swing — capping keeps every delta on a readable
    0-100 scale."""
    if not last_week_value or this_week_value is None:
        return None, None
    pct = round(abs(last_week_value - this_week_value) / last_week_value * 100)
    return min(pct, 100), this_week_value <= last_week_value


def _cached_fetch_all(cache_repository, table_name):
    """fetch_all(), memoized for the rest of THIS request only (Flask's
    per-request `g`) — the "Response/Resolution Time Duration" drilldown
    scopes call their own detail-rows function (the _SCOPE_HANDLERS
    "fetch" half) and _available_categories() (the "extra_template_kwargs"
    half) as two independent lambdas with no shared state (see
    dashboard.drilldown()), so without this, a single drilldown click
    scanned the same ~5-12k row table twice. Same "fetch once, share
    within the request" reasoning as IncidentService's ttl_cache-wrapped
    get_created_trend_rows()/get_closed_trend_rows() (see incident_service.py) —
    `g` instead of ttl_cache here since these are plain module functions,
    not methods on a persistent instance to hang a cache attribute off."""
    cache = g.setdefault("_fetch_all_cache", {})
    if table_name not in cache:
        cache[table_name] = cache_repository.fetch_all(table_name)
    return cache[table_name]


def _cached_fetch_columns(cache_repository, table_name, columns):
    """Same per-request memoization as _cached_fetch_all(), but for
    _response_time_duration_by_week()/_resolution_time_duration_by_week()
    specifically — both run on EVERY dashboard home-page load (not just a
    drilldown click) and only ever read 3 of these tables' 7 columns
    (category/iso_week/response_minutes or resolution_minutes). Measured
    live against the real cache: incident_resolution_time_details' own
    full SELECT * + dict-per-row (14k+ rows) cost ~45ms on every single
    page load for columns that were immediately discarded — same wasted-
    column pattern as get_congestion_top_devices() had (see
    BaseCacheRepository.fetch_columns()'s own docstring). Cached under a
    key that includes `columns` so it can't collide with
    _cached_fetch_all()'s own full-row cache entry for the same table
    (not that anything in the SAME request currently reads both, but
    nothing should have to assume that stays true)."""
    cache = g.setdefault("_fetch_columns_cache", {})
    key = (table_name, columns)
    if key not in cache:
        cache[key] = cache_repository.fetch_columns(table_name, columns)
    return cache[key]


def _available_categories(cache_repository, table_name, rows=None):
    """Distinct categories present in one of the 3 weekly-time/SLA
    caches, for that card's own Category filter dropdown — mirrors
    IncidentService.get_volume_trend_categories()'s "every distinct
    category, sorted" convention. Pass `rows` when the caller already
    fetched this table for something else this request (see
    _graph_cards_context()'s own docstring for why — avoids re-reading
    + re-scanning the same table more than once per page load)."""
    if rows is None:
        rows = _cached_fetch_all(cache_repository, table_name)
    return sorted({r["category"] for r in rows if r.get("category")})


def _combine_weekly_time_rows(rows_for_week):
    """Recombine several categories' pre-aggregated rows for the SAME
    week into one — count/min/max are simple sum/min/max (each is
    exactly decomposable that way), avg needs a count-weighted mean
    (sum(avg_i * count_i) / sum(count_i)), not a plain average of
    averages, or a category with 2 incidents would count as much as one
    with 200. With every category included this reproduces the exact
    same numbers the old ungrouped (no category column) query used to
    return directly — recombination isn't an approximation here."""
    total_count = sum(r["incident_count"] for r in rows_for_week)
    mins = [r["min_minutes"] for r in rows_for_week if r["min_minutes"] is not None]
    maxes = [r["max_minutes"] for r in rows_for_week if r["max_minutes"] is not None]
    weighted_avg_sum = sum(
        r["avg_minutes"] * r["incident_count"]
        for r in rows_for_week
        if r["avg_minutes"] is not None
    )
    avg_weighted_count = sum(
        r["incident_count"] for r in rows_for_week if r["avg_minutes"] is not None
    )
    return {
        "iso_week": rows_for_week[0]["iso_week"],
        "incident_count": total_count,
        "min_minutes": min(mins) if mins else None,
        "max_minutes": max(maxes) if maxes else None,
        "avg_minutes": (weighted_avg_sum / avg_weighted_count) if avg_weighted_count else None,
    }


def _weekly_time_week_view(row):
    return {
        "iso_week": row["iso_week"],
        "week_label": "Wk " + row["iso_week"].split("W")[-1],
        "incident_count": row["incident_count"],
        "avg_display": _format_minutes(row["avg_minutes"]),
        "min_display": _format_minutes(row["min_minutes"]),
        "max_display": _format_minutes(row["max_minutes"]),
    }


def _build_weekly_time_context(cache_repository, table_name, categories=None, weeks=None, rows=None):
    """Shared by both Response Time and Resolution Time — same cache
    shape (iso_week, category, incident_count, min/avg/max_minutes).
    `categories` (a list) narrows to those categories, recombined per
    week via _combine_weekly_time_rows(); empty/None means every
    category (see that function's own docstring for why this exactly
    reproduces the old un-filtered numbers rather than approximating
    them). None if fewer than 2 synced weeks exist yet (e.g. right
    after a fresh install, before the scheduler's first cycle
    completes).

    `weeks` (a list of ISO week strings, e.g. "2026-W37") picks which
    weeks the MIN/AVG/MAX table shows — any number of the 4 cached
    weeks, not just 2 (matches this card's own "Compare Weeks" checkbox
    list, which was never limited to picking exactly 2). Invalid/empty
    falls back to the latest two COMPLETE weeks, not literally "this
    week" — the current ISO week is still in progress (a handful of
    incidents synced so far, not a full 7 days), so comparing against
    it as if it were a finished week is what produced the absurd %
    deltas seen earlier. The trailing delta always compares the two
    MOST RECENT of whichever weeks are selected, same as when this was
    computed client-side.

    `rows` lets a caller pass an already-fetched table (see
    _available_categories()'s own docstring for why)."""
    all_rows = rows if rows is not None else cache_repository.fetch_all(table_name)
    all_rows = _filter_rows_by_categories(all_rows, categories)

    rows_by_week = {}
    for r in all_rows:
        rows_by_week.setdefault(r["iso_week"], []).append(r)
    rows = [
        _combine_weekly_time_rows(week_rows)
        for week_rows in rows_by_week.values()
    ]
    rows.sort(key=lambda r: r["iso_week"])
    if len(rows) < 2:
        return None

    current_iso_week = _now_local().strftime("%G-W%V")
    complete_rows = [r for r in rows if r["iso_week"] != current_iso_week]
    default_rows = complete_rows if len(complete_rows) >= 2 else rows
    default_isos = {default_rows[-2]["iso_week"], default_rows[-1]["iso_week"]}

    valid_isos = {r["iso_week"] for r in rows}
    picked_isos = [w for w in (weeks or []) if w in valid_isos]
    if picked_isos:
        selected_rows = sorted(
            (r for r in rows if r["iso_week"] in picked_isos), key=lambda r: r["iso_week"]
        )
    else:
        selected_rows = [default_rows[-2], default_rows[-1]]

    # "Compare Weeks" lets a user check any number of weeks, including
    # just one (e.g. unchecking the default pair down to a single week)
    # — there's nothing to diff a lone week against, so last_week stays
    # None and every delta below comes back None too (each of these
    # already treats a falsy last_week_value as "can't compute a %
    # change against it" — see _weekly_time_pct_delta()) instead of
    # crashing on selected_rows[-2] with only one row to index.
    this_week = selected_rows[-1]
    last_week = selected_rows[-2] if len(selected_rows) >= 2 else None
    avg_pct, avg_improved = _weekly_time_pct_delta(
        last_week["avg_minutes"] if last_week else None, this_week["avg_minutes"]
    )
    min_pct, min_improved = _weekly_time_pct_delta(
        last_week["min_minutes"] if last_week else None, this_week["min_minutes"]
    )
    max_pct, max_improved = _weekly_time_pct_delta(
        last_week["max_minutes"] if last_week else None, this_week["max_minutes"]
    )

    all_weeks = [
        {
            "iso_week": row["iso_week"],
            "week_label": "Wk " + row["iso_week"].split("W")[-1],
            "incident_count": row["incident_count"],
            "default_checked": row["iso_week"] in default_isos,
        }
        for row in rows
    ]

    return {
        "all_weeks": all_weeks,
        "selected_weeks": [_weekly_time_week_view(r) for r in selected_rows],
        "this_week": _weekly_time_week_view(this_week),
        "last_week": _weekly_time_week_view(last_week) if last_week else None,
        "this_week_is_partial": this_week["iso_week"] == current_iso_week,
        "avg_pct": avg_pct,
        "avg_improved": avg_improved,
        "min_pct": min_pct,
        "min_improved": min_improved,
        "max_pct": max_pct,
        "max_improved": max_improved,
    }


def _sla_pct(met_count, total_count):
    """2-decimal-place pass-rate, trimmed to a bare int when exact
    (100, not 100.0) — plain round() to a whole number was hiding real
    gaps behind a misleading "100%" (e.g. 1434/1439 is 99.65%, not
    100%), which is what the NOC actually needs to see here."""
    if not total_count:
        return None
    pct = round(met_count * 100.0 / total_count, 2)
    return int(pct) if pct == int(pct) else pct


def _combine_sla_compliance_rows(rows_for_week):
    """Same recombination idea as _combine_weekly_time_rows() but for
    SLA pass-rates — every count here is a simple sum (exactly
    decomposable), and both percentages are RE-DERIVED from the summed
    counts rather than averaged, since an average-of-percentages would
    weight a category with 2 incidents the same as one with 200."""
    incident_count = sum(r["incident_count"] for r in rows_for_week)
    response_met_count = sum(r["response_met_count"] for r in rows_for_week)
    resolution_known_count = sum(r["resolution_known_count"] for r in rows_for_week)
    resolution_met_count = sum(r["resolution_met_count"] for r in rows_for_week)
    return {
        "iso_week": rows_for_week[0]["iso_week"],
        "incident_count": incident_count,
        "response_met_count": response_met_count,
        "response_sla_pct": _sla_pct(response_met_count, incident_count),
        "resolution_known_count": resolution_known_count,
        "resolution_met_count": resolution_met_count,
        "resolution_sla_pct": _sla_pct(resolution_met_count, resolution_known_count),
    }


_SLA_CHART_WIDTH = 380.0
_SLA_CHART_HEIGHT = 140.0
_SLA_CHART_PAD_TOP = 12.0
_SLA_CHART_PAD_BOTTOM = 12.0
_SLA_CHART_PAD_LEFT = 4.0
_SLA_CHART_PAD_RIGHT = 4.0
_SLA_RESPONSE_COLOR = "var(--perf-cat-1)"
_SLA_RESOLUTION_COLOR = "var(--perf-cat-4)"


def _nice_sla_step(value_range):
    """1/5/10-percentage-point y-axis step — ported straight from the
    old client-side chart's own niceStep(), same thresholds, so moving
    this server-side doesn't change how granular the axis reads."""
    if value_range <= 10:
        return 2
    if value_range <= 20:
        return 5
    return 10


def _build_sla_chart_geometry(selected_rows):
    """SVG geometry for the SLA trend line — ported from
    performance.js's drawChart(), same 380x140 viewBox/padding and the
    same "at least 2 points" requirement (a single selected week can't
    draw a line). Points/tooltips follow the exact same
    .volume-point/.volume-tooltip markup Site-Down Duration's own
    server-rendered chart uses (get_site_down_duration_trend()) — no
    JS needed to make them hover-interactive, same as that card."""
    if len(selected_rows) < 2:
        return {"buckets": [], "grid_x": [], "tick_labels": [], "response_path": "", "resolution_path": ""}

    response_vals = [r["response_sla_pct"] if r["response_sla_pct"] is not None else 0 for r in selected_rows]
    resolution_vals = [r["resolution_sla_pct"] if r["resolution_sla_pct"] is not None else 0 for r in selected_rows]
    all_vals = response_vals + resolution_vals
    step = _nice_sla_step(max(all_vals) - min(all_vals) + 6)
    min_v = max(0, math.floor((min(all_vals) - 3) / step) * step)
    max_v = min(100, math.ceil((max(all_vals) + 3) / step) * step)
    if max_v == min_v:
        max_v = min_v + step

    n = len(selected_rows)
    plot_w = _SLA_CHART_WIDTH - _SLA_CHART_PAD_LEFT - _SLA_CHART_PAD_RIGHT
    plot_h = _SLA_CHART_HEIGHT - _SLA_CHART_PAD_TOP - _SLA_CHART_PAD_BOTTOM

    def x_pos(i):
        return _SLA_CHART_PAD_LEFT + (i / (n - 1)) * plot_w if n > 1 else _SLA_CHART_PAD_LEFT

    def y_pos(v):
        return _SLA_CHART_PAD_TOP + plot_h - ((v - min_v) / (max_v - min_v)) * plot_h

    x_positions = [x_pos(i) for i in range(n)]
    response_points = list(zip(x_positions, [y_pos(v) for v in response_vals]))
    resolution_points = list(zip(x_positions, [y_pos(v) for v in resolution_vals]))

    tick_values = []
    v = max_v
    while v >= min_v - 0.001:
        tick_values.append(v)
        v -= step

    buckets = []
    for i, row in enumerate(selected_rows):
        response_top_pct = round(y_pos(response_vals[i]) / _SLA_CHART_HEIGHT * 100, 1)
        resolution_top_pct = round(y_pos(resolution_vals[i]) / _SLA_CHART_HEIGHT * 100, 1)
        bucket_series = [
            {
                "label": "Response SLA",
                "color": _SLA_RESPONSE_COLOR,
                "value": row["response_sla_pct"],
                "top_pct": response_top_pct,
            },
            {
                "label": "Resolution SLA",
                "color": _SLA_RESOLUTION_COLOR,
                "value": row["resolution_sla_pct"],
                "top_pct": resolution_top_pct,
            },
        ]
        buckets.append({
            "bucket": "Wk " + row["iso_week"].split("W")[-1],
            "iso_week": row["iso_week"],
            "left_pct": round(x_positions[i] / _SLA_CHART_WIDTH * 100, 1),
            "series": bucket_series,
            "tooltip_anchor_pct": round(sum(s["top_pct"] for s in bucket_series) / len(bucket_series), 1),
            # For the click-to-spotlight handler (performance.js) — same
            # frac strings the pills above show, just per-point instead
            # of always the latest week.
            "response_frac": f"{row['response_met_count']}/{row['incident_count']}",
            "resolution_frac": f"{row['resolution_met_count']}/{row['resolution_known_count']}",
        })

    return {
        "buckets": buckets,
        "grid_x": x_positions,
        "tick_labels": [f"{round(v)}%" for v in tick_values],
        "response_path": _smooth_path(response_points),
        "resolution_path": _smooth_path(resolution_points),
    }


def _sla_compliance_week_breakdowns(categories=None, rows=None):
    """Per-(category, priority) SLA breakdown for EVERY cached week —
    "cache" here since it's built entirely from the same already-synced
    incident_sla_compliance_weekly rows the trend line itself reads, no
    per-incident table/query needed. Backs one pre-rendered popup per
    week (same "click week -> popup" pattern as Response/Resolution
    Time's own Duration popups, reusing that exact JS/CSS — see
    performance_cards.html's own comment on why), answering "which
    category/priority combo is driving this week's pass rate" instead
    of just the whole-week percentage the chart itself shows. Returns
    {iso_week: {"week_label": ..., "rows": [...]}}.

    `rows` lets a caller pass an already-fetched table (see
    _available_categories()'s own docstring for why)."""
    all_rows = (
        rows if rows is not None
        else _sla_compliance_weekly_cache_repository.fetch_all(_SLA_COMPLIANCE_WEEKLY_TABLE)
    )
    all_rows = _filter_rows_by_categories(all_rows, categories)

    by_week = {}
    for r in all_rows:
        by_week.setdefault(r["iso_week"], []).append(r)

    result = {}
    for iso_week, week_rows in by_week.items():
        rows_out = []
        for r in sorted(week_rows, key=lambda r: (r["category"], r["priority"])):
            rows_out.append({
                "category": r["category"],
                "priority": r["priority"],
                "response_met_count": r["response_met_count"],
                "incident_count": r["incident_count"],
                "response_sla_pct": r["response_sla_pct"],
                "resolution_met_count": r["resolution_met_count"],
                "resolution_known_count": r["resolution_known_count"],
                "resolution_sla_pct": r["resolution_sla_pct"],
                "not_graded_count": r.get("not_graded_count") or 0,
            })
        result[iso_week] = {
            "week_label": "Wk " + iso_week.split("W")[-1],
            "rows": rows_out,
        }
    return result


def _sla_root_cause_label(row):
    return str(row.get("root_cause_category") or "").strip() or "Not Assigned"


def _sla_compliance_root_cause_breakdowns(categories=None):
    """Count root causes for incidents that missed Response or Resolution SLA.

    Keep the occurrence-week anchor, category filters and unassigned causes.
    The drilldown uses the same root_cause metric predicate.
    """
    rows = _sla_compliance_details_cache_repository.fetch_all(_SLA_COMPLIANCE_DETAILS_TABLE)
    rows = _filter_rows_by_categories(rows, categories)

    counts_by_week = {}
    for r in rows:
        iso_week = r.get("iso_week")
        if not iso_week or not _SLA_COMPLIANCE_METRICS["root_cause"](r):
            continue
        category = _sla_root_cause_label(r)
        week_counts = counts_by_week.setdefault(iso_week, {})
        counts = week_counts.setdefault(category, {"count": 0, "response_not_met": 0, "resolution_not_met": 0})
        counts["count"] += 1
        counts["response_not_met"] += int(r.get("overdue_response") == 1)
        counts["resolution_not_met"] += int(r.get("overdue") == 1)

    return {
        iso_week: sorted(
            ({"category": category, **counts} for category, counts in week_counts.items()),
            key=lambda c: c["count"],
            reverse=True,
        )
        for iso_week, week_counts in counts_by_week.items()
    }


def _build_sla_compliance_context(categories=None, weeks=None, rows=None):
    """SLA Compliance card — two real pass-rates (response/resolution)
    plus a trend line fed with actual weekly percentages (up to 4
    points). `categories` (a list) narrows to those categories,
    recombined per week via _combine_sla_compliance_rows(); empty/None
    means every category. `weeks` (a list of ISO week strings) narrows
    which weeks feed the trend line/pills; empty/None means every
    cached week (this card's default has always been "show the whole
    trend", not a this-week/last-week comparison like the other two
    cards). None if no synced weeks exist yet.

    `rows` lets a caller pass an already-fetched table (see
    _available_categories()'s own docstring for why)."""
    all_rows = (
        rows if rows is not None
        else _sla_compliance_weekly_cache_repository.fetch_all(_SLA_COMPLIANCE_WEEKLY_TABLE)
    )
    all_rows = _filter_rows_by_categories(all_rows, categories)

    rows_by_week = {}
    for r in all_rows:
        rows_by_week.setdefault(r["iso_week"], []).append(r)
    rows = [
        _combine_sla_compliance_rows(week_rows)
        for week_rows in rows_by_week.values()
    ]
    rows.sort(key=lambda r: r["iso_week"])
    if not rows:
        return None

    valid_isos = {r["iso_week"] for r in rows}
    picked_isos = [w for w in (weeks or []) if w in valid_isos]
    selected_rows = (
        sorted((r for r in rows if r["iso_week"] in picked_isos), key=lambda r: r["iso_week"])
        if picked_isos
        else rows
    )
    selected_isos = {r["iso_week"] for r in selected_rows}

    all_weeks = [
        {
            "iso_week": row["iso_week"],
            "week_label": "Wk " + row["iso_week"].split("W")[-1],
            "default_checked": row["iso_week"] in selected_isos,
        }
        for row in rows
    ]

    # Response SLA's denominator (COUNT(*)) is never 0 for a week that
    # has a row here at all, but resolution_sla_pct's denominator
    # (resolution_known_count) legitimately can be — a brand new week
    # with no incidents that have gotten a real resolution verdict yet
    # — round(None) crashes, so both are guarded; "not enough data
    # yet" should read as "--", not a misleading "0%".
    latest = selected_rows[-1] if selected_rows else rows[-1]
    this_week = {
        "iso_week": latest["iso_week"],
        "week_label": "Wk " + latest["iso_week"].split("W")[-1],
        "response_sla_pct": latest["response_sla_pct"],
        "response_frac": f"{latest['response_met_count']}/{latest['incident_count']}",
        "resolution_sla_pct": latest["resolution_sla_pct"],
        "resolution_frac": f"{latest['resolution_met_count']}/{latest['resolution_known_count']}",
    }

    return {"all_weeks": all_weeks, "this_week": this_week, **_build_sla_chart_geometry(selected_rows)}


def _resolve_duration_selection(badge_type, bucket_tokens_map, bucket_labels):
    """Shared parsing behind both Response Time's and Resolution Time's
    "By Duration" drilldowns — combines the drilldown page's own
    "Filter by Duration" checkboxes (`duration_bucket`, a list of bucket
    labels, and `week`, both real query params only present once that
    form has actually been submitted) with whatever badge_type a popup
    link provided ("{token}[,{token2},...]_{iso_week}", e.g.
    "lt1m_2026-W36" from a single click, or "lt1m,1m_15m_2026-W36" once
    more than one bucket is checked in that filter) — the checkboxes
    take priority when present, since checking a different bucket while
    already on the drilldown page is a fresher choice than whatever
    badge_type the page first loaded with, and it's the same fixed week
    either way (this filter only ever changes which bucket(s) show, not
    the week — the week stays whatever the popup was opened for).

    Returns (set of matched bucket indices, iso_week), or (None, None)
    if neither the checkboxes nor badge_type yield anything usable/
    well-formed."""
    duration_buckets = request.args.getlist("duration_bucket")
    week = request.args.get("week")
    if duration_buckets and week:
        indices = {bucket_labels.index(label) for label in duration_buckets if label in bucket_labels}
        return (indices, week) if indices else (None, None)

    if not badge_type:
        return None, None
    try:
        tokens_str, iso_week = badge_type.rsplit("_", 1)
    except ValueError:
        return None, None
    token_to_label = {v: k for k, v in bucket_tokens_map.items()}
    indices = set()
    for token in tokens_str.split(","):
        if token not in token_to_label:
            return None, None
        indices.add(bucket_labels.index(token_to_label[token]))
    return indices, iso_week


# Response Time card's duration-bucket breakdown — how many incidents'
# response time fell into each bucket, per selected week (a seconds/
# minutes-scale sibling of IncidentService's own ≤15m/16m-4h/... buckets,
# which are hour-scale and tuned for Site-Down/Incident-Volume durations,
# not something this short).
_RESPONSE_DURATION_BUCKET_LABELS = ("≤1m", "1m-15m", "15m-1h", "1h-4h", "4h-24h", ">24h")

# Bucket label -> URL-safe token (badge `type`), same "can't ride '<'/'>'
# in a query string" reasoning as IncidentService._DURATION_BUCKET_TOKENS.
# Combined with the row's own iso_week string (e.g. "lt1m_2026-W36") —
# see _response_time_duration_by_week()/_response_time_duration_details().
_RESPONSE_DURATION_BUCKET_TOKENS = {
    "≤1m": "lt1m",
    "1m-15m": "1m_15m",
    "15m-1h": "15m_1h",
    "1h-4h": "1h_4h",
    "4h-24h": "4h_24h",
    ">24h": "gt24h",
}


def _response_duration_bucket_index(minutes):
    """Minutes -> index into _RESPONSE_DURATION_BUCKET_LABELS (0=≤1m..5=>24h)."""
    if minutes <= 1:
        return 0
    if minutes < 15:
        return 1
    if minutes < 60:
        return 2
    if minutes < 240:
        return 3
    if minutes < 1440:
        return 4
    return 5


def _bucket_response_time_details(rows, iso_weeks):
    """response_minutes (already computed by incident_response_time_details.sql,
    no re-derivation needed) bucketed by _RESPONSE_DURATION_BUCKET_LABELS,
    one count-list per selected ISO week. Returns {iso_week: [6 counts]}."""
    counts = {w: [0] * len(_RESPONSE_DURATION_BUCKET_LABELS) for w in iso_weeks}
    for r in rows:
        iso_week = r.get("iso_week")
        if iso_week not in counts:
            continue
        minutes = r.get("response_minutes")
        if minutes is None or minutes < 0:
            continue
        counts[iso_week][_response_duration_bucket_index(minutes)] += 1
    return counts


def _response_time_duration_by_week(categories=None, weeks=None):
    """Per-week duration-bucket breakdown for the Response Time card's
    "By Duration" popup — click a week's header in the MIN/AVG/MAX table
    to open a modal listing how many incidents fell into each of
    _RESPONSE_DURATION_BUCKET_LABELS that week, each count linking to the
    real incidents behind it (dashboard.py's _SCOPE_HANDLERS["Response
    Time Duration"] -> _response_time_duration_details()) — same
    click-a-label-to-open-a-popup pattern as Incident Volume's own "By
    Category" per-weekday modals, just no chart.

    Shares the Response Time card's own Category (`categories`) and
    Compare Weeks (`weeks`) filter state — `weeks` here is a list of
    iso_week strings (e.g. "2026-W36"), matching _build_weekly_time_context()'s
    own selection keys, so the SAME iso_week values key both this dict
    and response_time.selected_weeks — the template looks a week's
    breakdown up by that shared key
    (response_time_duration_by_week[w.iso_week]) rather than assuming
    the two lists stay in matching order. Keyed by iso_week string
    (empty dict if no synced rows exist yet)."""
    rows = _cached_fetch_columns(
        _response_time_details_cache_repository,
        _RESPONSE_TIME_DETAILS_TABLE,
        _RESPONSE_TIME_DETAIL_COLUMNS,
    )
    rows = _filter_rows_by_categories(rows, categories)

    valid_isos = sorted({r.get("iso_week") for r in rows if r.get("iso_week")})
    if not valid_isos:
        return {}

    current_iso_week = _now_local().strftime("%G-W%V")
    complete_isos = [w for w in valid_isos if w != current_iso_week]
    default_pool = complete_isos if len(complete_isos) >= 2 else valid_isos
    default_isos = default_pool[-2:]

    picked_isos = sorted(w for w in (weeks or []) if w in valid_isos)
    selected_isos = picked_isos if picked_isos else default_isos

    counts = _bucket_response_time_details(rows, selected_isos)

    return {
        iso: {
            "iso_week": iso,
            "week_label": "Wk " + iso.split("W")[-1],
            "buckets": [
                {
                    "label": label,
                    "count": counts[iso][i],
                    "badge_type": f"{_RESPONSE_DURATION_BUCKET_TOKENS[label]}_{iso}",
                }
                for i, label in enumerate(_RESPONSE_DURATION_BUCKET_LABELS)
            ],
        }
        for iso in selected_isos
    }


def _response_time_extreme_incident_by_week(categories, weeks):
    """Which real incident(s) the MIN/AVG/MAX table's own MIN row AND
    MAX row actually came from, per selected week — for those cells'
    own hover tooltip (requested: touching MIN/MAX should show
    Incident ID + Category, not just the bare number, and let you
    click through to that incident's own drilldown row).
    _combine_weekly_time_rows()'s own min_minutes/max_minutes is
    min/max(per-category mins/maxes), which is mathematically the same
    single lowest/highest response_minutes value among these
    per-incident detail rows once the SAME category filter is applied —
    so this doesn't need to re-derive or double-check that number, just
    find which row(s) achieve it. Same week-selection resolution as
    _response_time_duration_by_week() above (latest 2 complete weeks by
    default), so this dict's own keys always match response_time.
    selected_weeks' iso_week values. More than one incident can share
    the exact extreme (a tie) — all are returned, newest occurred_at
    first; the template shows just the first with a "+N more" note if
    there's more than one. Each incident also carries its own
    `badge_type` — the exact same "{bucket_token}_{iso_week}" token
    _response_time_duration_by_week()'s own per-bucket drilldown already
    uses, so "view in drilldown" reuses that existing page/route as-is
    rather than needing a new one scoped to a single incident_id.

    Returns (min_result, max_result) — computed together in ONE pass
    per week instead of two separate calls each re-filtering/
    re-grouping the same rows (confirmed live via cProfile: the old
    min-call/max-call shape cost roughly double for no reason, since
    finding both ends of the same per-week value list is one O(n) scan,
    not two). Same output shape as before per dict, unchanged."""
    rows = _cached_fetch_columns(
        _response_time_details_cache_repository,
        _RESPONSE_TIME_DETAILS_TABLE,
        _RESPONSE_TIME_DETAIL_COLUMNS,
    )
    rows = _filter_rows_by_categories(rows, categories)

    valid_isos = sorted({r.get("iso_week") for r in rows if r.get("iso_week")})
    if not valid_isos:
        return {}, {}

    current_iso_week = _now_local().strftime("%G-W%V")
    complete_isos = [w for w in valid_isos if w != current_iso_week]
    default_pool = complete_isos if len(complete_isos) >= 2 else valid_isos
    default_isos = default_pool[-2:]

    picked_isos = sorted(w for w in (weeks or []) if w in valid_isos)
    selected_isos = picked_isos if picked_isos else default_isos

    def _entries_for(week_rows, target_minutes, iso):
        top = sorted(
            (r for r in week_rows if r["response_minutes"] == target_minutes),
            key=lambda r: r.get("occurred_at") or "",
            reverse=True,
        )
        return [
            {
                "incident_id": r.get("incident_id") or "",
                "category": r.get("category") or "Uncategorized",
                "response_display": _format_minutes(r["response_minutes"]),
                "badge_type": (
                    f"{_RESPONSE_DURATION_BUCKET_TOKENS[_RESPONSE_DURATION_BUCKET_LABELS[_response_duration_bucket_index(r['response_minutes'])]]}"
                    f"_{iso}"
                ),
            }
            for r in top
        ]

    min_result, max_result = {}, {}
    for iso in selected_isos:
        week_rows = [
            r for r in rows if r.get("iso_week") == iso and r.get("response_minutes") is not None
        ]
        if not week_rows:
            continue
        values = [r["response_minutes"] for r in week_rows]
        min_result[iso] = _entries_for(week_rows, min(values), iso)
        max_result[iso] = _entries_for(week_rows, max(values), iso)
    return min_result, max_result


def _response_time_duration_details(badge_type=None, categories=None):
    """Rows behind one or more bucket counts in the Response Time "By
    Duration" popup/drilldown — badge_type is
    "{token}[,{token2},...]_{iso_week}" (e.g. "lt1m_2026-W36" from a
    single popup click, or multiple comma-joined tokens once the
    drilldown's own "Filter by Duration" checkboxes select more than
    one bucket — see _resolve_duration_selection(), which also lets
    those checkboxes override badge_type once submitted). `categories`
    narrows further to that specific category, same as the card's own
    Category filter. None if the selection isn't well-formed either
    way. Every row (optionally category-filtered) if there's no
    selection at all — a bare "show everything" request. Sorted
    fastest-first so the incident actually driving a MIN sits at the
    top."""
    rows = _cached_fetch_all(_response_time_details_cache_repository, _RESPONSE_TIME_DETAILS_TABLE)
    rows = _filter_rows_by_categories(rows, categories)

    def _with_display(matched_rows):
        out = []
        for r in matched_rows:
            row = dict(r)
            minutes = row.get("response_minutes") or 0
            if minutes < 1:
                row["response_display"] = f"{round(minutes * 60)}s"
            elif minutes < 60:
                row["response_display"] = f"{minutes:.1f}m"
            else:
                h, m = divmod(round(minutes), 60)
                row["response_display"] = f"{h}h {m}m"
            out.append(row)
        out.sort(key=lambda r: r.get("response_minutes") or 0)
        return out

    if not badge_type and not request.args.getlist("duration_bucket"):
        return _with_display(rows)

    bucket_indices, iso_week = _resolve_duration_selection(
        badge_type, _RESPONSE_DURATION_BUCKET_TOKENS, _RESPONSE_DURATION_BUCKET_LABELS
    )
    if bucket_indices is None:
        return None

    matched = [
        r for r in rows
        if r.get("iso_week") == iso_week
        and r.get("response_minutes") is not None
        and r["response_minutes"] >= 0
        and _response_duration_bucket_index(r["response_minutes"]) in bucket_indices
    ]
    return _with_display(matched)


def _response_time_duration_extra_kwargs(badge_type):
    """extra_template_kwargs for the "Response Time Duration" drilldown
    — the Category and "Filter by Duration" widgets both need to know
    what's currently selected/available to render their checkboxes."""
    bucket_indices, iso_week = _resolve_duration_selection(
        badge_type, _RESPONSE_DURATION_BUCKET_TOKENS, _RESPONSE_DURATION_BUCKET_LABELS
    )
    if bucket_indices is None:
        bucket_indices, iso_week = set(), request.args.get("week", "")
    return {
        "available_categories": _available_categories(
            _response_time_details_cache_repository, _RESPONSE_TIME_DETAILS_TABLE
        ),
        "selected_categories": request.args.getlist("category"),
        "iso_week": iso_week,
        "duration_options": [
            {"label": label, "checked": i in bucket_indices}
            for i, label in enumerate(_RESPONSE_DURATION_BUCKET_LABELS)
        ],
    }


# Resolution Time card's duration-bucket breakdown — same bucket scale
# as Response Time's own _RESPONSE_DURATION_BUCKET_LABELS above (kept as
# its own separate copy rather than shared, matching this codebase's
# existing "near-identical query/logic per feature" convention, e.g.
# incident_created_trend_by_ids.sql vs incident_closed_trend_by_ids.sql).
_RESOLUTION_DURATION_BUCKET_LABELS = ("≤1m", "1m-15m", "15m-1h", "1h-4h", "4h-24h", ">24h")

_RESOLUTION_DURATION_BUCKET_TOKENS = {
    "≤1m": "lt1m",
    "1m-15m": "1m_15m",
    "15m-1h": "15m_1h",
    "1h-4h": "1h_4h",
    "4h-24h": "4h_24h",
    ">24h": "gt24h",
}


def _resolution_duration_bucket_index(minutes):
    """Minutes -> index into _RESOLUTION_DURATION_BUCKET_LABELS (0=≤1m..5=>24h)."""
    if minutes <= 1:
        return 0
    if minutes < 15:
        return 1
    if minutes < 60:
        return 2
    if minutes < 240:
        return 3
    if minutes < 1440:
        return 4
    return 5


def _bucket_resolution_time_details(rows, iso_weeks):
    """resolution_minutes (already computed by
    incident_resolution_time_details.sql, no re-derivation needed)
    bucketed by _RESOLUTION_DURATION_BUCKET_LABELS, one count-list per
    selected ISO week. Returns {iso_week: [6 counts]}."""
    counts = {w: [0] * len(_RESOLUTION_DURATION_BUCKET_LABELS) for w in iso_weeks}
    for r in rows:
        iso_week = r.get("iso_week")
        if iso_week not in counts:
            continue
        minutes = r.get("resolution_minutes")
        if minutes is None or minutes < 0:
            continue
        counts[iso_week][_resolution_duration_bucket_index(minutes)] += 1
    return counts


def _resolution_time_duration_by_week(categories=None, weeks=None):
    """Per-week duration-bucket breakdown for the Resolution Time card's
    "By Duration" popup — same click-a-blue-week-header-to-open-a-popup
    pattern as Response Time's own _response_time_duration_by_week().
    Keyed by iso_week string, same reasoning as that function's own
    docstring for why (matches response_time.selected_weeks keys
    exactly so the template can look a week's breakdown up directly,
    rather than assuming matching list order)."""
    rows = _cached_fetch_columns(
        _resolution_time_details_cache_repository,
        _RESOLUTION_TIME_DETAILS_TABLE,
        _RESOLUTION_TIME_DETAIL_COLUMNS,
    )
    rows = _filter_rows_by_categories(rows, categories)

    valid_isos = sorted({r.get("iso_week") for r in rows if r.get("iso_week")})
    if not valid_isos:
        return {}

    current_iso_week = _now_local().strftime("%G-W%V")
    complete_isos = [w for w in valid_isos if w != current_iso_week]
    default_pool = complete_isos if len(complete_isos) >= 2 else valid_isos
    default_isos = default_pool[-2:]

    picked_isos = sorted(w for w in (weeks or []) if w in valid_isos)
    selected_isos = picked_isos if picked_isos else default_isos

    counts = _bucket_resolution_time_details(rows, selected_isos)

    return {
        iso: {
            "iso_week": iso,
            "week_label": "Wk " + iso.split("W")[-1],
            "buckets": [
                {
                    "label": label,
                    "count": counts[iso][i],
                    "badge_type": f"{_RESOLUTION_DURATION_BUCKET_TOKENS[label]}_{iso}",
                }
                for i, label in enumerate(_RESOLUTION_DURATION_BUCKET_LABELS)
            ],
        }
        for iso in selected_isos
    }


def _resolution_time_extreme_incident_by_week(categories, weeks):
    """Same mechanism as Response Time's own
    _response_time_extreme_incident_by_week() — see that function's own
    docstring for the full rationale (ties, week-resolution, why
    badge_type reuses the existing per-bucket drilldown instead of a
    new route, and why min/max are computed together in one pass) —
    just resolution_minutes/_RESOLUTION_DURATION_BUCKET_*/
    _resolution_duration_bucket_index() in place of their Response Time
    equivalents. Returns (min_result, max_result)."""
    rows = _cached_fetch_columns(
        _resolution_time_details_cache_repository,
        _RESOLUTION_TIME_DETAILS_TABLE,
        _RESOLUTION_TIME_DETAIL_COLUMNS,
    )
    rows = _filter_rows_by_categories(rows, categories)

    valid_isos = sorted({r.get("iso_week") for r in rows if r.get("iso_week")})
    if not valid_isos:
        return {}, {}

    current_iso_week = _now_local().strftime("%G-W%V")
    complete_isos = [w for w in valid_isos if w != current_iso_week]
    default_pool = complete_isos if len(complete_isos) >= 2 else valid_isos
    default_isos = default_pool[-2:]

    picked_isos = sorted(w for w in (weeks or []) if w in valid_isos)
    selected_isos = picked_isos if picked_isos else default_isos

    def _entries_for(week_rows, target_minutes, iso):
        top = sorted(
            (r for r in week_rows if r["resolution_minutes"] == target_minutes),
            key=lambda r: r.get("occurred_at") or "",
            reverse=True,
        )
        return [
            {
                "incident_id": r.get("incident_id") or "",
                "category": r.get("category") or "Uncategorized",
                "response_display": _format_minutes(r["resolution_minutes"]),
                "badge_type": (
                    f"{_RESOLUTION_DURATION_BUCKET_TOKENS[_RESOLUTION_DURATION_BUCKET_LABELS[_resolution_duration_bucket_index(r['resolution_minutes'])]]}"
                    f"_{iso}"
                ),
            }
            for r in top
        ]

    min_result, max_result = {}, {}
    for iso in selected_isos:
        week_rows = [
            r for r in rows if r.get("iso_week") == iso and r.get("resolution_minutes") is not None
        ]
        if not week_rows:
            continue
        values = [r["resolution_minutes"] for r in week_rows]
        min_result[iso] = _entries_for(week_rows, min(values), iso)
        max_result[iso] = _entries_for(week_rows, max(values), iso)
    return min_result, max_result


def _resolution_time_duration_details(badge_type=None, categories=None):
    """Rows behind one or more bucket counts in the Resolution Time "By
    Duration" popup/drilldown — badge_type is
    "{token}[,{token2},...]_{iso_week}" (e.g. "lt1m_2026-W36" from a
    single popup click, or multiple comma-joined tokens once the
    drilldown's own "Filter by Duration" checkboxes select more than
    one bucket — see _resolve_duration_selection(), which also lets
    those checkboxes override badge_type once submitted). `categories`
    narrows further to that specific category, same as the card's own
    Category filter. None if the selection isn't well-formed either
    way. Every row (optionally category-filtered) if there's no
    selection at all — a bare "show everything" request. Sorted
    fastest-first so the incident actually driving a MIN sits at the
    top."""
    rows = _cached_fetch_all(_resolution_time_details_cache_repository, _RESOLUTION_TIME_DETAILS_TABLE)
    rows = _filter_rows_by_categories(rows, categories)

    def _with_display(matched_rows):
        out = []
        for r in matched_rows:
            row = dict(r)
            minutes = row.get("resolution_minutes") or 0
            if minutes < 1:
                row["resolution_display"] = f"{round(minutes * 60)}s"
            elif minutes < 60:
                row["resolution_display"] = f"{minutes:.1f}m"
            else:
                h, m = divmod(round(minutes), 60)
                row["resolution_display"] = f"{h}h {m}m"
            out.append(row)
        out.sort(key=lambda r: r.get("resolution_minutes") or 0)
        return out

    if not badge_type and not request.args.getlist("duration_bucket"):
        return _with_display(rows)

    bucket_indices, iso_week = _resolve_duration_selection(
        badge_type, _RESOLUTION_DURATION_BUCKET_TOKENS, _RESOLUTION_DURATION_BUCKET_LABELS
    )
    if bucket_indices is None:
        return None

    matched = [
        r for r in rows
        if r.get("iso_week") == iso_week
        and r.get("resolution_minutes") is not None
        and r["resolution_minutes"] >= 0
        and _resolution_duration_bucket_index(r["resolution_minutes"]) in bucket_indices
    ]
    return _with_display(matched)


def _resolution_time_duration_extra_kwargs(badge_type):
    """extra_template_kwargs for the "Resolution Time Duration"
    drilldown — the Category and "Filter by Duration" widgets both need
    to know what's currently selected/available to render their
    checkboxes."""
    bucket_indices, iso_week = _resolve_duration_selection(
        badge_type, _RESOLUTION_DURATION_BUCKET_TOKENS, _RESOLUTION_DURATION_BUCKET_LABELS
    )
    if bucket_indices is None:
        bucket_indices, iso_week = set(), request.args.get("week", "")
    return {
        "available_categories": _available_categories(
            _resolution_time_details_cache_repository, _RESOLUTION_TIME_DETAILS_TABLE
        ),
        "selected_categories": request.args.getlist("category"),
        "iso_week": iso_week,
        "duration_options": [
            {"label": label, "checked": i in bucket_indices}
            for i, label in enumerate(_RESOLUTION_DURATION_BUCKET_LABELS)
        ],
    }


# SLA Compliance card's per-week Category x Priority popup — one cell
# (e.g. "Response Met" for BSS Hardware/Low, week 2026-W36) links here.
# badge_type is "{metric}_{iso_week}"; metric selects which of the 3
# per-incident booleans a row must satisfy. `category`/`priority` are
# single values (not lists) in request.args, since one popup cell is
# always exactly one category/priority pair — see
# _sla_compliance_week_breakdowns() in _performance_cards_context() for
# where the popup's own links are built.
_SLA_COMPLIANCE_METRICS = {
    "resp_met": lambda r: r.get("overdue_response") == 0,
    "res_met": lambda r: r.get("overdue") == 0,
    "res_known": lambda r: r.get("overdue") is not None,
    "not_graded": lambda r: r.get("overdue") is None,
    "total": lambda r: True,
    "root_cause": lambda r: r.get("overdue_response") == 1 or r.get("overdue") == 1,
    "root_cause_resp": lambda r: r.get("overdue_response") == 1,
    "root_cause_res": lambda r: r.get("overdue") == 1,
}

# Which week column each metric's iso_week in a badge_type ("{metric}_
# {iso_week}") should be matched against — must be the SAME anchor
# incident_sla_compliance_weekly.sql used to compute that metric's own
# count, or the drilldown shows a different, mismatched set of incidents
# than the number that was clicked (confirmed live: Resolution Met's
# "21/43" cell linked to only 17 rows under the old single-iso_week
# filtering, since resolution_known_count is closed_at-anchored but the
# filter was issue_occurred_at-anchored — see
# incident_sla_compliance_details.sql's own header for the full story).
_SLA_COMPLIANCE_METRIC_WEEK_COLUMN = {
    "resp_met": "response_iso_week",
    "res_met": "resolution_iso_week",
    "res_known": "resolution_iso_week",
    "not_graded": "iso_week",
    # "total" backs the popup's "All Incidents" link, which is literally
    # hyperlinked to row.incident_count (see performance_cards.html) —
    # and incident_count comes from response_stats in
    # incident_sla_compliance_weekly.sql, i.e. it's created_at-anchored,
    # the SAME source as response_met_count. Confirmed live this isn't
    # theoretical: 7 of 70 real category/week combos already disagreed
    # between occurred_at-week and created_at-week totals.
    "total": "response_iso_week",
    "root_cause": "iso_week",
}


def _sla_target_lookup():
    """SLA policy rules (sla_policy cache, object_327) indexed for a
    per-incident lookup — one dict keyed by (category, support_level,
    priority) for L1 NOC/L3 Internal rules, one keyed by (category,
    support_level, site_grade) for L2 On-Site rules (see sla_policy.sql's
    own header: a rule keys off exactly one of the two, never both).
    Both dicts share the same rule dict as their value."""
    by_priority = {}
    by_site_grade = {}
    for rule in _sla_policy_cache_repository.fetch_all(_SLA_POLICY_TABLE):
        if rule.get("priority"):
            by_priority[(rule["category"], rule["support_level"], rule["priority"])] = rule
        if rule.get("site_grade"):
            by_site_grade[(rule["category"], rule["support_level"], rule["site_grade"])] = rule
    return by_priority, by_site_grade


def _sla_target_display(row, by_priority, by_site_grade):
    """"{Priority or Site Grade} ({resolution target})" for one incident
    row, matching Streamline's own SLA column (e.g. "Medium (8 Hours)")
    — None if no rule matches (row missing category/support_level, or a
    combination not covered by any active rule)."""
    category = row.get("category")
    support_level = row.get("support_level")
    if support_level == "L2 On-Site":
        key_value = row.get("site_grade")
        rule = by_site_grade.get((category, support_level, key_value)) if key_value else None
    else:
        key_value = row.get("priority")
        rule = by_priority.get((category, support_level, key_value)) if key_value else None
    if not rule:
        return None
    target = rule["resolution_time"]
    target_display = int(target) if target == int(target) else target
    return f"{key_value} ({target_display} {rule['measure_resolution_time']})"


def _sla_compliance_details(badge_type=None):
    """Rows behind one cell in the SLA Compliance card's per-week
    popup. None if badge_type isn't well-formed ("{metric}_{iso_week}",
    metric one of _SLA_COMPLIANCE_METRICS' keys). Every synced row if
    there's no badge_type at all — a bare "show everything" request,
    same convention as _response_time_duration_details()."""
    rows = _sla_compliance_details_cache_repository.fetch_all(_SLA_COMPLIANCE_DETAILS_TABLE)
    by_priority, by_site_grade = _sla_target_lookup()

    def _with_display(matched_rows):
        out = []
        for r in matched_rows:
            row = dict(r)
            row["root_cause_category"] = _sla_root_cause_label(row)
            row["response_sla_display"] = (
                "Missed" if row.get("overdue_response") == 1
                else "Met" if row.get("overdue_response") == 0 else "-"
            )
            row["resolution_sla_display"] = (
                "Missed" if row.get("overdue") == 1
                else "Met" if row.get("overdue") == 0 else "Not Graded"
            )
            row["sla_target_display"] = _sla_target_display(row, by_priority, by_site_grade)
            out.append(row)
        out.sort(key=lambda r: r.get("occurred_at") or "")
        return out

    if not badge_type:
        return _with_display(rows)

    try:
        metric, iso_week = badge_type.rsplit("_", 1)
    except ValueError:
        return None
    metric_fn = _SLA_COMPLIANCE_METRICS.get(metric)
    if metric_fn is None:
        return None

    category = request.args.get("category")
    priority = request.args.get("priority")
    root_cause = request.args.get("root_cause")
    if metric.startswith("root_cause"):
        rows = _filter_rows_by_categories(rows, request.args.getlist("sla_compliance_category"))
    week_column = _SLA_COMPLIANCE_METRIC_WEEK_COLUMN.get(metric, "iso_week")
    matched = [
        r for r in rows
        if r.get(week_column) == iso_week
        and (not category or r.get("category") == category)
        and (not priority or r.get("priority") == priority)
        and (not metric.startswith("root_cause") or root_cause is None or _sla_root_cause_label(r) == root_cause)
        and metric_fn(r)
    ]
    return _with_display(matched)


def _performance_cards_context():
    """Template vars for the Performance section on the Overall
    Dashboard (moved here from the now-removed standalone Performance
    page) — Response Time, Resolution Time, SLA Compliance, Site-Down
    Duration, and Top Site Down are the real cards; the other 2
    (Site-Down Root Cause Breakdown, Root Cause Breakdown) stay static
    sample data (see app/templates/dashboard/partials/performance_cards.html
    — no root-cause taxonomy exists in the real incident data yet, see
    incident_site_down_root_cause.sql for why)."""
    selected_response_time_categories = request.args.getlist("response_time_category")
    selected_resolution_time_categories = request.args.getlist("resolution_time_category")
    selected_sla_compliance_categories = request.args.getlist("sla_compliance_category")
    selected_response_time_weeks = request.args.getlist("response_time_week")
    selected_resolution_time_weeks = request.args.getlist("resolution_time_week")
    selected_sla_compliance_weeks = request.args.getlist("sla_compliance_week")

    # Each of these 3 tables backs 2-3 separate pieces of this section
    # (chart/context, category-filter list, and — for SLA Compliance —
    # the per-week popup too) — fetched once here and passed via
    # `rows=` into each consumer instead of each one re-reading the
    # same SQLite table, same "_graph_cards_context() already does this
    # for the 2 biggest tables" pattern.
    response_time_weekly_rows = _response_time_weekly_cache_repository.fetch_all(
        _RESPONSE_TIME_WEEKLY_TABLE
    )
    resolution_time_weekly_rows = _resolution_time_weekly_cache_repository.fetch_all(
        _RESOLUTION_TIME_WEEKLY_TABLE
    )
    sla_compliance_weekly_rows = _sla_compliance_weekly_cache_repository.fetch_all(
        _SLA_COMPLIANCE_WEEKLY_TABLE
    )
    # Computed once each (not once per MIN + once per MAX) — see these
    # functions' own docstrings for why that used to cost roughly double
    # for no reason.
    response_time_min_incident_by_week, response_time_max_incident_by_week = (
        _response_time_extreme_incident_by_week(
            selected_response_time_categories, selected_response_time_weeks
        )
    )
    resolution_time_min_incident_by_week, resolution_time_max_incident_by_week = (
        _resolution_time_extreme_incident_by_week(
            selected_resolution_time_categories, selected_resolution_time_weeks
        )
    )
    return {
        "response_time": _build_weekly_time_context(
            _response_time_weekly_cache_repository,
            _RESPONSE_TIME_WEEKLY_TABLE,
            selected_response_time_categories,
            selected_response_time_weeks,
            rows=response_time_weekly_rows,
        ),
        "response_time_categories": _available_categories(
            _response_time_weekly_cache_repository,
            _RESPONSE_TIME_WEEKLY_TABLE,
            rows=response_time_weekly_rows,
        ),
        "selected_response_time_categories": selected_response_time_categories,
        "selected_response_time_weeks": selected_response_time_weeks,
        "response_time_duration_by_week": _response_time_duration_by_week(
            selected_response_time_categories,
            selected_response_time_weeks,
        ),
        "response_time_min_incident_by_week": response_time_min_incident_by_week,
        "response_time_max_incident_by_week": response_time_max_incident_by_week,
        "resolution_time": _build_weekly_time_context(
            _resolution_time_weekly_cache_repository,
            _RESOLUTION_TIME_WEEKLY_TABLE,
            selected_resolution_time_categories,
            selected_resolution_time_weeks,
            rows=resolution_time_weekly_rows,
        ),
        "resolution_time_categories": _available_categories(
            _resolution_time_weekly_cache_repository,
            _RESOLUTION_TIME_WEEKLY_TABLE,
            rows=resolution_time_weekly_rows,
        ),
        "selected_resolution_time_categories": selected_resolution_time_categories,
        "selected_resolution_time_weeks": selected_resolution_time_weeks,
        "resolution_time_duration_by_week": _resolution_time_duration_by_week(
            selected_resolution_time_categories,
            selected_resolution_time_weeks,
        ),
        "resolution_time_min_incident_by_week": resolution_time_min_incident_by_week,
        "resolution_time_max_incident_by_week": resolution_time_max_incident_by_week,
        "sla_compliance": _build_sla_compliance_context(
            selected_sla_compliance_categories,
            selected_sla_compliance_weeks,
            rows=sla_compliance_weekly_rows,
        ),
        "sla_compliance_week_breakdowns": _sla_compliance_week_breakdowns(
            selected_sla_compliance_categories, rows=sla_compliance_weekly_rows
        ),
        "sla_compliance_root_cause_breakdowns": _sla_compliance_root_cause_breakdowns(
            selected_sla_compliance_categories
        ),
        "sla_compliance_categories": _available_categories(
            _sla_compliance_weekly_cache_repository,
            _SLA_COMPLIANCE_WEEKLY_TABLE,
            rows=sla_compliance_weekly_rows,
        ),
        "selected_sla_compliance_categories": selected_sla_compliance_categories,
        "selected_sla_compliance_weeks": selected_sla_compliance_weeks,
        "sla_policy_rules": _sla_policy_cache_repository.fetch_all(_SLA_POLICY_TABLE),
        "site_down_duration": incident_service.get_site_down_duration_trend(
            request.args.getlist("site_down_duration_week"),
            request.args.getlist("duration_bucket"),
        ),
        "selected_site_down_duration_weeks": request.args.getlist("site_down_duration_week"),
        "selected_duration_buckets": request.args.getlist("duration_bucket"),
        "top_site_down": incident_service.get_top_site_down(request.args.getlist("top_site_down_week")),
        "root_cause_breakdown": incident_service.get_site_down_root_cause_breakdown(
            site_code=request.args.get("root_cause_site") or None,
            weeks=request.args.getlist("top_site_down_week"),
        ),
        "root_cause_weekly_breakdown": incident_service.get_site_down_root_cause_weekly_breakdown(
            site_code=request.args.get("root_cause_site") or None,
            weeks=request.args.getlist("top_site_down_week"),
        ),
        "selected_root_cause_site": request.args.get("root_cause_site") or None,
        "root_cause_week_breakdown": incident_service.get_site_down_root_cause_week_breakdown(
            duration_bucket=request.args.get("root_cause_bucket") or None,
            duration_buckets=request.args.getlist("duration_bucket"),
            weeks=request.args.getlist("site_down_duration_week"),
        ),
        "root_cause_week_table": incident_service.get_site_down_root_cause_week_table(
            duration_bucket=request.args.get("root_cause_bucket") or None,
            weeks=request.args.getlist("site_down_duration_week"),
        ),
        "selected_root_cause_bucket": request.args.get("root_cause_bucket") or None,
    }


def _graph_cards_context(incident_status_rows=None):
    """Template vars for the 3 graph cards (see graph_cards.html), built
    from this request's age_bucket/volume_category/closed_category/
    volume_week/closed_week query params. Shared by index() (full page)
    and graph_cards() (the AJAX fragment each card's header dropdown
    fetches instead of reloading the whole dashboard).

    incident_created_trend/incident_closed_trend are each fetched here
    ONCE (get_created_trend_rows()/get_closed_trend_rows()) and passed
    into both the trend chart and its category-list call below — each
    fetch_all() is ~100ms against these tables' 12-15k+ rows, so fetching
    twice (chart + category list) doubled that cost for no reason.

    `incident_status_rows`, if given (see IncidentService.
    get_incident_status_rows()), is threaded into get_incident_age_chart()
    instead of it fetching incident_by_status again — index() already
    fetches this table once for get_incident_counts()."""
    selected_age_buckets = request.args.getlist("age_bucket")
    selected_volume_categories = request.args.getlist("volume_category")
    selected_closed_categories = request.args.getlist("closed_category")
    selected_volume_weeks = request.args.getlist("volume_week")
    selected_closed_weeks = request.args.getlist("closed_week")
    available_weeks = incident_service.get_available_weeks()
    created_trend_rows = incident_service.get_created_trend_rows()
    closed_trend_rows = incident_service.get_closed_trend_rows()
    # Category/Severity/Province/Vendor's weekly breakdown, computed in
    # ONE combined pass over created_trend_rows instead of 4 separate
    # passes — confirmed byte-for-byte identical output to the old
    # 4-separate-calls approach on real data before this was wired in
    # here. See _incident_volume_multi_field_breakdown()'s own docstring.
    # The per-weekday equivalent (_incident_volume_multi_field_day_
    # breakdowns()) is NOT computed here on purpose — it's only needed by
    # whichever ONE of the 7 per-weekday popups a visitor actually opens,
    # fetched on demand by volume_day_popup() below instead of embedding
    # all 7 (all 4 fields each) into every page load, which used to make
    # up ~64% of this page's ~950KB HTML.
    volume_breakdowns = incident_service._incident_volume_multi_field_breakdown(
        selected_volume_categories, selected_volume_weeks, rows=created_trend_rows
    )
    return {
        "incident_age_chart": incident_service.get_incident_age_chart(
            selected_age_buckets, rows=incident_status_rows
        ),
        "incident_age_worklog_by_bucket": incident_service.get_worklog_age_availability(),
        "selected_age_buckets": selected_age_buckets,
        "incident_closed_trend": incident_service.get_incident_closed_trend(
            selected_closed_categories, selected_closed_weeks, rows=closed_trend_rows
        ),
        "closed_trend_categories": incident_service.get_closed_trend_categories(rows=closed_trend_rows),
        "selected_closed_categories": selected_closed_categories,
        "selected_closed_weeks": selected_closed_weeks,
        "incident_volume_trend": incident_service.get_incident_volume_trend(
            selected_volume_categories, selected_volume_weeks, rows=created_trend_rows
        ),
        "volume_category_breakdown": volume_breakdowns["categories"],
        "volume_severity_breakdown": volume_breakdowns["severities"],
        "volume_province_breakdown": volume_breakdowns["provinces"],
        "volume_vendor_breakdown": volume_breakdowns["vendors"],
        "volume_trend_categories": incident_service.get_volume_trend_categories(rows=created_trend_rows),
        "selected_volume_categories": selected_volume_categories,
        "selected_volume_weeks": selected_volume_weeks,
        "available_weeks": available_weeks,
        # Skip index 0 ("This week", still in progress) — same reasoning
        # as _resolve_selected_weeks() (incident_service.py): default to
        # the latest two COMPLETE weeks, not the partial current one.
        "default_weeks": [w["iso"] for w in available_weeks[1:3]],
    }


def _cross_card_filter_passthrough():
    """Every other Performance-section card's own filter state — every
    graph_cards.html form carries all of these as hidden inputs too (so
    applying an Age/Volume/Closed filter doesn't clear them). index()
    already gets the real versions from _performance_cards_context(), so
    this exists only for graph_cards()'s AJAX fragment route below, which
    doesn't otherwise call that function. Without this, a second
    consecutive AJAX-only filter click (no full page reload in between)
    would read the PREVIOUS swap's hidden inputs — rendered blank, since
    they weren't in that response's context — and silently drop whatever
    was selected on those other cards. A lightweight passthrough dict
    (not the real get_top_site_down()/_build_weekly_time_context()/
    _build_sla_compliance_context(), which each read/recombine their
    whole cache) is all the hidden input actually needs."""
    return {
        "selected_site_down_duration_weeks": request.args.getlist("site_down_duration_week"),
        "selected_duration_buckets": request.args.getlist("duration_bucket"),
        "top_site_down": {"selected_weeks": request.args.getlist("top_site_down_week")},
        "selected_response_time_categories": request.args.getlist("response_time_category"),
        "selected_response_time_weeks": request.args.getlist("response_time_week"),
        "selected_resolution_time_categories": request.args.getlist("resolution_time_category"),
        "selected_resolution_time_weeks": request.args.getlist("resolution_time_week"),
        "selected_sla_compliance_categories": request.args.getlist("sla_compliance_category"),
        "selected_sla_compliance_weeks": request.args.getlist("sla_compliance_week"),
    }


@dashboard_bp.route("/graph-cards")
def graph_cards():
    """HTML fragment for just the 3 graph cards, re-rendered from the
    query string's filters. Fetched by graph_cards.js so applying a
    card's dropdown filter swaps that row in place instead of reloading
    the whole dashboard."""
    return render_template(
        "dashboard/partials/graph_cards.html",
        **_graph_cards_context(),
        **_cross_card_filter_passthrough(),
    )


@dashboard_bp.route("/volume-day-popup/<int:day_index>")
def volume_day_popup(day_index):
    """HTML fragment for ONE weekday's Incident Volume popup body
    (Category/Severity/Province/Vendor tabs), fetched by graph_cards.js
    the first time that weekday's x-axis label is clicked, instead of
    all 7 weekdays being pre-rendered into every page load (see
    _graph_cards_context()'s own note). Same volume_category/volume_week
    filters as the graph cards, so the popup always matches whatever's
    currently applied there."""
    if not 0 <= day_index <= 6:
        abort(404)
    selected_volume_categories = request.args.getlist("volume_category")
    selected_volume_weeks = request.args.getlist("volume_week")
    created_trend_rows = incident_service.get_created_trend_rows()
    volume_day_breakdowns = incident_service._incident_volume_multi_field_day_breakdowns(
        selected_volume_categories, selected_volume_weeks, rows=created_trend_rows
    )
    return render_template(
        "dashboard/partials/_volume_day_popup_body.html",
        day_breakdown=volume_day_breakdowns["categories"][day_index],
        day_severity_breakdown=volume_day_breakdowns["severities"][day_index],
        day_province_breakdown=volume_day_breakdowns["provinces"][day_index],
        day_vendor_breakdown=volume_day_breakdowns["vendors"][day_index],
        selected_volume_categories=selected_volume_categories,
    )


def _graph_card_filter_passthrough():
    """The 3 graph cards' own filter state — every performance_cards.html
    filter form carries these as hidden inputs too (mirrors
    _cross_card_filter_passthrough()'s reverse direction), so applying a
    Performance-card filter via the /performance-cards AJAX fragment
    below doesn't blank out whichever Age/Volume/Closed filter is
    currently active on the graph cards. Lightweight (no cache reads,
    same reasoning as _cross_card_filter_passthrough() itself) — the
    hidden inputs only need the selected VALUES, not each graph card's
    whole recomputed context."""
    return {
        "selected_age_buckets": request.args.getlist("age_bucket"),
        "selected_volume_categories": request.args.getlist("volume_category"),
        "selected_volume_weeks": request.args.getlist("volume_week"),
        "selected_closed_categories": request.args.getlist("closed_category"),
        "selected_closed_weeks": request.args.getlist("closed_week"),
    }


@dashboard_bp.route("/performance-cards")
def performance_cards():
    """HTML fragment for just the Performance section, re-rendered from
    the query string's filters. Fetched by performance.js so applying a
    card's filter swaps this section in place instead of reloading the
    whole dashboard — same pattern as graph_cards() above.

    available_weeks/default_weeks are computed here too, not just
    reused from _graph_cards_context() — that function only runs for a
    FULL page load, never for this AJAX fragment route, so without
    this performance_cards.html's own "Compare Weeks" checkbox list
    silently rendered empty the instant a user clicked Apply (looping
    over an undefined Jinja variable raises nothing, it's just zero
    iterations) — confirmed live: the checkboxes show up fine on first
    page load, then vanish after Apply re-fetches this same fragment."""
    available_weeks = incident_service.get_available_weeks()
    return render_template(
        "dashboard/partials/performance_cards.html",
        **_performance_cards_context(),
        **_graph_card_filter_passthrough(),
        available_weeks=available_weeks,
        default_weeks=[w["iso"] for w in available_weeks[1:3]],
    )


@dashboard_bp.route("/")
def index():
    _log_dashboard_data_freshness()
    refresh_seconds = current_app.config["DASHBOARD_LOG_INTERVAL_SECONDS"]
    # Rounded up so the reload never fires before its boundary.
    # offset_seconds=120 lands this after every background sync job's
    # own staggered offset, so the reload never competes with a sync
    # write and always picks up freshly-synced data.
    next_refresh_seconds = math.ceil(
        seconds_until_next_aligned_time(
            refresh_seconds, current_app.config["TIMEZONE"], offset_seconds=120
        )
    )

    lazy_performance = (
        current_app.config.get("DASHBOARD_LAZY_PERFORMANCE", True)
        and request.args.get("load_performance") != "1"
    )
    performance_context = (
        _cross_card_filter_passthrough() if lazy_performance else _performance_cards_context()
    )
    incident_status_rows = incident_service.get_incident_status_rows()
    return render_template(
        "dashboard/index.html",
        isp_pop_counts=alarm_service.get_isp_pop_counts(),
        eze_counts=alarm_service.get_eze_counts(),
        tct_counts=alarm_service.get_tct_counts(),
        incident_counts=incident_service.get_incident_counts(rows=incident_status_rows),
        **_graph_cards_context(incident_status_rows=incident_status_rows),
        **performance_context,
        lazy_performance=lazy_performance,
        performance_fallback_url=url_for(
            "dashboard.index",
            **{**request.args.to_dict(flat=False), "load_performance": "1"},
        ),
        incwo_counts=incwo_service.get_incwo_counts(),
        incwo_all_resolved_count=incwo_service.get_all_resolved_count(),
        vip_site_counts=vip_alarm_service.get_counts(),
        ran_main_ac_alarm_counts=ran_main_ac_alarm_service.get_counts(),
        ran_site_down_counts=ran_site_down_service.get_counts(),
        ran_tech_down_counts=ran_tech_down_service.get_counts(),
        ran_voltage_counts=ran_voltage_service.get_counts(),
        mentor_site_counts=mentor_site_service.get_counts(),
        next_refresh_seconds=next_refresh_seconds,
    )


@dashboard_bp.route("/congestion")
def congestion():
    """Standalone page showing just the Top Congestion Devices card —
    requested for a fixed, bookmarkable URL (/congestion) that doesn't
    load the whole dashboard (ISP POP/EZE/TCT/Performance section/etc.)
    just to see this one card, e.g. for a dedicated wallboard display.
    Same data/filter/auto-reload behavior as the card on dashboard/
    index.html, just rendered on its own — see dashboard/congestion.html's
    own comment for the two small differences (filter form posts back to
    THIS route, and skips the cross-card hidden-field passthrough that
    only matters when other cards share the page)."""
    refresh_seconds = current_app.config["DASHBOARD_LOG_INTERVAL_SECONDS"]
    next_refresh_seconds = math.ceil(
        seconds_until_next_aligned_time(
            refresh_seconds, current_app.config["TIMEZONE"], offset_seconds=120
        )
    )
    return render_template(
        "dashboard/congestion.html",
        congestion_top_devices=alarm_service.get_congestion_top_devices(
            congestion_weeks=request.args.getlist("congestion_top_week")
        ),
        next_refresh_seconds=next_refresh_seconds,
    )


def _fetch_rows(scope, alarm_type, date_from="", date_to="", congestion_week=""):
    """Rows for `scope`, optionally narrowed to one badge's alarm type(s)
    (case-insensitive) and/or a Down Time date range. Both dates are ISO
    format, so a plain string comparison on the first 10 characters
    sorts correctly without parsing.

    `alarm_type` is usually one raw value, but accepts a comma-separated
    list too — the TCT Congestion badge merges the 'bandwidth' and
    'congestion' raw alarm types into one count (see
    AlarmService.get_tct_counts()), so its drilldown link sends both
    ("bandwidth,congestion") to show every row the badge's number
    actually counted, not just the ones literally named 'congestion'.

    "Congestion History" is the one exception: its dashboard card ranks
    DEVICES, not alarm types (see AlarmService.get_congestion_top_devices()),
    so a badge click sends a device name in `alarm_type` instead of a raw
    alarm type — matched against `device_name` here rather than `alarm`.
    Also fetched via its own get_congestion_device_interface_summary()
    (one row per Interface, Total = flap count) rather than the generic
    alarm-event shape every other scope uses here — see that method's
    own docstring for why a per-alarm row stopped making sense for this
    one once Down Time/Restored Time/Alarm Name/Outage/Note/Action were
    removed from this view.

    `congestion_week` is the OTHER way into this same scope with no
    device at all — the card's own "Wk 37 · Wk 38 · ..." caption links
    straight to one week's rows across EVERY device, summarized the same
    one-row-per-(Device, Interface) way as the device case (see
    get_congestion_week_interface_summary()) — Total here is that WEEK's
    own flap count, not the whole-window one. Only consulted when
    `alarm_type` is empty — a device click always wins if both are
    somehow present.

    Interface-summary rows (both cases above) have no down_time/alarm
    field at all, so the generic alarm-type/date-range filtering below
    is skipped entirely for this scope — it's already fully resolved by
    whichever of the two methods above was called."""
    if scope == "Congestion History" and alarm_type:
        return alarm_service.get_congestion_device_interface_summary(alarm_type)
    if scope == "Congestion History" and congestion_week:
        return alarm_service.get_congestion_week_interface_summary(congestion_week)
    if scope == "Congestion History":
        return []

    fetch_details = _LIVE_ALARM_SCOPES.get(scope)
    if not fetch_details:
        return None
    rows = fetch_details()
    if alarm_type:
        wanted = {t.strip().upper() for t in alarm_type.split(",") if t.strip()}
        rows = [r for r in rows if (r.get("alarm") or "").strip().upper() in wanted]
    return filter_calendar_dates(rows, "down_time", date_from, date_to)


def _safe_filename(scope, alarm_type):
    """Build the CSV filename from `scope`/`alarm_type`, keeping only
    [A-Za-z0-9_-] so neither can inject into the response header."""
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


@dashboard_bp.route("/alarms/acknowledge", methods=["POST"])
def acknowledge_alarm():
    """Acknowledge/Modify popup submit target for the EZE / TCT / ISP
    POP drilldown tables. Writes straight to the real MSSQL row via
    AlarmService.acknowledge_note() (which returns that row's own final
    note/ack/ab/md/mb straight from MSSQL's own trailing SELECT, the same
    round trip as the write), then patches just that ONE row into the
    local cache via AlarmSyncService.apply_acknowledge_result() — not a
    second live MSSQL round trip to re-fetch the whole table, which is
    what this used to do (sync_scope()), before the redirect would
    otherwise show the stale cached row. `source` (isp_pop/eze/tct/
    it_node, see alarms.html's own `source` var) tells
    apply_acknowledge_result() which ONE of its 4 cache tables that row
    lives in. `row_id` is TBL_PPD.ID, not RTID (RTID repeats across
    unrelated rows). `username` is never captured server-side (no login
    system); it's whatever the popup's JS read from that browser's
    localStorage."""
    row_id = request.form.get("id", "").strip()
    tt_inc_wo_id = request.form.get("tt_inc_wo_id", "").strip()
    note = request.form.get("note", "").strip()
    username = request.form.get("username", "").strip()
    source = request.form.get("source", "").strip()

    if row_id and username and (tt_inc_wo_id or note):
        result = alarm_service.acknowledge_note(row_id, tt_inc_wo_id, note, username)
        alarm_sync_service.apply_acknowledge_result(source, row_id, result)

    return redirect(request.referrer or url_for("dashboard.index"))


@dashboard_bp.route("/alarms/clear", methods=["POST"])
def clear_alarm():
    """Clear Alarm popup submit target for the EZE / TCT / ISP POP
    drilldown tables' Action menu — writes the clear to MSSQL, then
    removes that one row from the local cache directly via
    AlarmSyncService.apply_clear() (a cleared alarm no longer belongs in
    an active-only cache table at all) instead of a full sync_scope()
    re-fetch, same reasoning as acknowledge_alarm()."""
    row_id = request.form.get("id", "").strip()
    username = request.form.get("username", "").strip()
    source = request.form.get("source", "").strip()

    if row_id and username:
        alarm_service.clear_alarm(row_id, username)
        alarm_sync_service.apply_clear(source, row_id)

    return redirect(request.referrer or url_for("dashboard.index"))


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
            extra = (
                handler["extra_template_kwargs"](alarm_type)
                if "extra_template_kwargs" in handler
                else {}
            )
            if rows is not None and scope in _DATE_FILTERABLE_SCOPES:
                rows = _filter_by_occurred_at(rows, date_from, date_to)
                extra = {
                    **extra,
                    "date_from": date_from,
                    "date_to": date_to,
                    "date_from_display": format_short_date(date_from),
                    "date_to_display": format_short_date(date_to),
                    "date_range_label": _date_range_label(date_from, date_to),
                }
            elif rows is not None and scope in _WO_CREATED_AT_FILTERABLE_SCOPES:
                rows = _filter_by_wo_created_at(rows, date_from, date_to)
                extra = {
                    **extra,
                    "scope": scope,
                    "date_from": date_from,
                    "date_to": date_to,
                    "date_from_display": format_short_date(date_from),
                    "date_to_display": format_short_date(date_to),
                    "date_range_label": _date_range_label(date_from, date_to),
                }

            row_cap = handler.get("row_cap")
            if rows is not None and row_cap and len(rows) > row_cap:
                extra["row_cap_notice"] = (
                    f"Showing the newest {row_cap} of {len(rows)} rows — use a "
                    "badge above or the date filter to narrow it down."
                )
                rows = rows[:row_cap]

            return render_template(
                handler["template"], title=title, label=label, rows=rows, **extra
            )
        # None + none_is_404 falls through to the empty-state template.

    congestion_week_raw = request.args.get("congestion_week", "")
    rows = _fetch_rows(scope, alarm_type, date_from, date_to, congestion_week=congestion_week_raw)
    if rows is not None:
        row_cap_notice = None
        extra = {}
        if scope == "Congestion History":
            # Both ways into this scope — a device bar's badge click
            # (get_congestion_device_interface_summary()) or the card's
            # own "Wk 37 · Wk 38 · ..." caption
            # (get_congestion_week_interface_summary()) — already return
            # one row per (Device, Interface) with their own real
            # total_count (flap-episode count), already ranked highest
            # first. A device has at most a few dozen interfaces (no cap
            # needed), but the week view spans EVERY device — give it
            # its own Top 10/20/All row-count filter (template only
            # shows this control when alarm_type is empty).
            extra = {
                "congestion_interface_summary": True,
                "congestion_week": congestion_week_raw,
            }
            if not alarm_type:
                row_limit_raw = request.args.get("row_limit", "")
                row_limit = int(row_limit_raw) if row_limit_raw in ("10", "20") else None
                if row_limit and len(rows) > row_limit:
                    row_cap_notice = (
                        f"Showing the top {row_limit} of {len(rows)} interfaces by flap "
                        "count — use the row-count filter above to narrow it down."
                    )
                    rows = rows[:row_limit]
                extra["selected_row_limit"] = row_limit
        return render_template(
            "drilldown/alarms.html",
            title=title,
            label=label,
            scope=scope,
            alarm_type=alarm_type,
            rows=rows,
            source=_ALARM_SOURCE[scope],
            date_from=date_from,
            date_to=date_to,
            date_from_display=format_short_date(date_from),
            date_to_display=format_short_date(date_to),
            date_range_label=_date_range_label(date_from, date_to),
            default_ack_username=_DEFAULT_ACK_USERNAME,
            row_cap_notice=row_cap_notice,
            **extra,
        )

    # Not a live scope — static placeholder card, renders the empty state.
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
        elif rows is not None and scope in _WO_CREATED_AT_FILTERABLE_SCOPES:
            rows = _filter_by_wo_created_at(rows, date_from, date_to)
        return _csv_response(rows, handler["csv_columns"], _safe_filename(scope, alarm_type))

    rows = _fetch_rows(
        scope, alarm_type, date_from, date_to, congestion_week=request.args.get("congestion_week", "")
    )
    if rows is None:
        return Response("Unknown or unavailable scope", status=404)

    if scope == "Congestion History":
        # Both ways into this scope already return one row per (Device,
        # Interface) with their own real total_count — see _fetch_rows()'s
        # own docstring.
        columns = _CONGESTION_INTERFACE_SUMMARY_CSV_COLUMNS
    else:
        columns = _CSV_COLUMNS_BY_SOURCE[_ALARM_SOURCE[scope]]
    return _csv_response(rows, columns, _safe_filename(scope, alarm_type))


@dashboard_bp.get("/dashboard/worklog/<badge_type>")
def age_worklog_fragment(badge_type):
    result = incident_service.get_worklog_by_age_bucket(badge_type)
    if badge_type not in result:
        abort(404)
    return render_template("dashboard/partials/age_worklog_table.html", incidents=result[badge_type])
