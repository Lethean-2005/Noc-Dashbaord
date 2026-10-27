"""Local SQLite cache (instance/localstorage.db).

Mirrors MSSQL/Postgres data locally so request-time reads (dashboard
cards, drilldowns, CSV export) never hit those databases directly.
Background schedulers keep it in sync.
"""

import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from flask import current_app, g, has_request_context

# One row per active alarm, normalized across MSSQL sources — see
# app/services/alarm/alarm_sync_service.py. it_node_alarm_cache (the "IT
# NODE" card) shares this shape but leaves device/pop fields blank.
# congestion_history_cache is the one exception to "active alarm" in this
# group's own name — it holds HISTORICAL (including long-cleared)
# Congestion rows, synced by AlarmSyncService.sync_congestion_history()
# on its own slower schedule (congestion_history_scheduler.py), not the
# active-only sync_all() the other 4 tables get — but the row SHAPE is
# identical, so it reuses this same schema/columns rather than needing
# its own. restored_time (added alongside congestion_history_cache) is
# usually blank for the 4 active-only tables (their alarms haven't
# cleared yet) but is what makes a HISTORICAL row's own actual outage
# duration computable at all (down_time -> restored_time), rather than
# the misleading "elapsed since now" AlarmService._with_outage() uses
# for a still-active alarm.
ALARM_CACHE_TABLES = (
    "isp_pop_alarm_cache",
    "eze_alarm_cache",
    "tct_alarm_cache",
    "it_node_alarm_cache",
    "congestion_history_cache",
)

_ALARM_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        id TEXT, alarm TEXT, alarm_name TEXT, device_name TEXT, ip_address TEXT, pop_name TEXT,
        pop_code TEXT, province TEXT, pro_owner TEXT, down_time TEXT, restored_time TEXT, root_cause TEXT, rtid TEXT,
        interface TEXT, source_group TEXT, additional_info TEXT, note TEXT,
        ack TEXT, ab TEXT, mb TEXT, md TEXT
    )
"""

_ALARM_CACHE_COLUMNS = {
    "id",
    "alarm",
    "alarm_name",
    "device_name",
    "ip_address",
    "pop_name",
    "pop_code",
    "province",
    "pro_owner",
    "down_time",
    "restored_time",
    "root_cause",
    "rtid",
    "interface",
    "source_group",
    "additional_info",
    "note",
    "ack",
    "ab",
    "mb",
    "md",
}

# Per-(device, interface) "flap episode" count over congestion_history_
# cache's own window — a flap episode groups consecutive Congestion rows
# for the SAME device AND interface into ONE incident when the gap
# between one row's restored_time and the next row's down_time is small
# (see AlarmSyncService._compute_flap_counts()'s own grouping rule),
# instead of counting each individual clear/re-trigger blip separately.
# Grouped by (device, interface) rather than device alone — a device
# with several interfaces each congesting independently would otherwise
# have unrelated interfaces' events merged into one shared episode just
# because they happened close together in time on the same device.
# Recomputed and overwritten every time sync_congestion_history() runs —
# never read by any route/template today; exists so the number is ready
# in the local cache if/when it's ever surfaced, without recomputing it
# from the full ~9-10k row table on demand.
CONGESTION_FLAP_CACHE_TABLES = ("congestion_flap_counts_cache",)

_CONGESTION_FLAP_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        device_name TEXT, interface TEXT, flap_count INTEGER, updated_at TEXT,
        PRIMARY KEY (device_name, interface)
    )
"""

_CONGESTION_FLAP_CACHE_COLUMNS = {"device_name", "interface", "flap_count", "updated_at"}

# One row per Site (Postgres object_160), curated to the columns the
# dashboard needs — see app/services/site/site_sync_service.py.
# Province/District/Commune/Village are resolved names, not raw FK ids;
# physical_location_name/_address come from a join to object_308.
SITE_CACHE_TABLES = ("site_cache",)

_SITE_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        id INTEGER PRIMARY KEY, name TEXT, status TEXT, type TEXT,
        site_grade TEXT, fra_site_name TEXT, standard_code TEXT, site_priority TEXT,
        site_strategic_type TEXT,
        province TEXT, district TEXT, commune TEXT, village TEXT,
        physical_location INTEGER, physical_location_name TEXT,
        physical_location_address TEXT, p_lat REAL, p_lon REAL, hub_site TEXT,
        actual_ran_vendor INTEGER
    )
"""

_SITE_CACHE_COLUMNS = {
    "id",
    "name",
    "status",
    "type",
    "site_grade",
    "fra_site_name",
    "standard_code",
    "site_priority",
    "site_strategic_type",
    "province",
    "district",
    "commune",
    "village",
    "physical_location",
    "physical_location_name",
    "physical_location_address",
    "p_lat",
    "p_lon",
    "hub_site",
    "actual_ran_vendor",
}

# One row per (Incident, Site) pair currently 'new' or 'in_progress' —
# the joined drilldown detail behind every Incident-column badge. A
# multi-site incident is more than one row here, sharing the same
# incident_id — see app/database/queries/incident_by_status.sql and
# app/services/incident/incident_sync_service.py.
INCIDENT_STATUS_CACHE_TABLES = ("incident_by_status",)

_INCIDENT_STATUS_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        incident_id TEXT, incident_numeric_id INTEGER, incident_status TEXT, wo_id TEXT,
        wo_numeric_id INTEGER, wo_created_at TEXT, wo_status TEXT, resolved_at TEXT, responsible_team TEXT,
        support_level TEXT, site_name TEXT, site_code TEXT,
        occurred_at TEXT, overdue TEXT, category TEXT,
        l1_noc_investigation_result TEXT, nms TEXT, hub_site TEXT, site_grade TEXT,
        province TEXT, district TEXT, commune TEXT,
        PRIMARY KEY (incident_id, site_code)
    )
"""

_INCIDENT_STATUS_CACHE_COLUMNS = {
    "incident_id",
    "incident_numeric_id",
    "incident_status",
    "wo_id",
    "wo_numeric_id",
    "wo_created_at",
    "wo_status",
    "resolved_at",
    "responsible_team",
    "support_level",
    "site_name",
    "site_code",
    "occurred_at",
    "overdue",
    "category",
    "l1_noc_investigation_result",
    "nms",
    "hub_site",
    "site_grade",
    "province",
    "district",
    "commune",
}

# Same shape as incident_by_status, scoped to VIP/VVIP sites with
# status != 'closed'. Kept separate rather than widening
# incident_by_status (unpaginated, shared by several services — widening
# it directly caused a real outage).
VIP_INCIDENT_STATUS_CACHE_TABLES = ("vip_incident_status",)

_VIP_INCIDENT_STATUS_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        incident_id TEXT, incident_numeric_id INTEGER, incident_status TEXT, wo_id TEXT,
        wo_numeric_id INTEGER, wo_created_at TEXT, wo_status TEXT, resolved_at TEXT, responsible_team TEXT,
        support_level TEXT, site_name TEXT, site_code TEXT,
        occurred_at TEXT, overdue TEXT, category TEXT,
        l1_noc_investigation_result TEXT, nms TEXT, hub_site TEXT, site_grade TEXT,
        province TEXT, district TEXT, commune TEXT,
        PRIMARY KEY (incident_id, site_code)
    )
"""

_VIP_INCIDENT_STATUS_CACHE_COLUMNS = {
    "incident_id",
    "incident_numeric_id",
    "incident_status",
    "wo_id",
    "wo_numeric_id",
    "wo_created_at",
    "wo_status",
    "resolved_at",
    "support_level",
    "responsible_team",
    "site_name",
    "site_code",
    "occurred_at",
    "overdue",
    "category",
    "l1_noc_investigation_result",
    "nms",
    "hub_site",
    "site_grade",
    "province",
    "district",
    "commune",
}

# One row per INC-WO not yet 'closed' — see
# app/database/queries/inc_wo_by_status.sql. wo_id can be NULL for a
# freshly-created work order (SQLite allows multiple NULLs in a
# PRIMARY KEY column). inc_wo_site_down / inc_wo_category_power share
# this shape, each scoped to one work-order category.
INC_WO_STATUS_CACHE_TABLES = ("inc_wo_by_status", "inc_wo_site_down", "inc_wo_category_power")

_INC_WO_STATUS_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        incident_id TEXT, incident_numeric_id INTEGER, incident_status TEXT, wo_id TEXT PRIMARY KEY,
        wo_numeric_id INTEGER, wo_created_at TEXT, wo_status TEXT, resolved_at TEXT,
        incident_category TEXT, site_name TEXT, site_code TEXT, overdue TEXT, support_level TEXT,
        responsible_team TEXT,
        fault_description TEXT, nms TEXT, hub_site TEXT, site_grade TEXT,
        province TEXT, district TEXT, commune TEXT
    )
"""

_INC_WO_STATUS_CACHE_COLUMNS = {
    "incident_id",
    "incident_numeric_id",
    "incident_status",
    "wo_id",
    "wo_numeric_id",
    "wo_created_at",
    "wo_status",
    "resolved_at",
    "incident_category",
    "site_name",
    "site_code",
    "overdue",
    "support_level",
    "responsible_team",
    "fault_description",
    "nms",
    "hub_site",
    "site_grade",
    "province",
    "district",
    "commune",
}

# One row per INC-WO Resolved while its parent Incident is still
# In-Progress — the "INC-WO Resolved" card. See
# app/database/queries/inc_wo_resolved.sql.
INC_WO_RESOLVED_CACHE_TABLES = ("inc_wo_resolved",)

_INC_WO_RESOLVED_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        incident_id TEXT, incident_numeric_id INTEGER, incident_status TEXT, wo_id TEXT PRIMARY KEY,
        wo_numeric_id INTEGER, wo_created_at TEXT, wo_status TEXT, resolved_at TEXT, site_name TEXT, site_code TEXT,
        overdue TEXT, support_level TEXT, responsible_team TEXT, fault_description TEXT, nms TEXT,
        hub_site TEXT, site_grade TEXT, province TEXT, district TEXT, commune TEXT
    )
"""

_INC_WO_RESOLVED_CACHE_COLUMNS = {
    "incident_id",
    "incident_numeric_id",
    "incident_status",
    "wo_id",
    "wo_numeric_id",
    "wo_created_at",
    "wo_status",
    "resolved_at",
    "site_name",
    "site_code",
    "overdue",
    "support_level",
    "responsible_team",
    "fault_description",
    "nms",
    "hub_site",
    "site_grade",
    "province",
    "district",
    "commune",
}

# One row per VIP/VVIP, On Air Site (TBL_SITE joined to TBL_NE on MSSQL) —
# see app/database/queries/vip_site_cache.sql and
# app/services/vip/vip_site_sync_service.py for the sync. site_code is the
# primary key: scoped to On Air + not-removed-NE, this query returns one
# row per site in practice (verified against live MSSQL — no site_code
# repeats), unlike the old SITE_INFO-backed version this replaced, which
# needed a GUID id column since that source table did have real duplicate
# SITE_CODEs.
VIP_SITE_CACHE_TABLES = ("vip_site_cache",)

_VIP_SITE_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        site_code TEXT PRIMARY KEY, site_name TEXT, status TEXT,
        province TEXT, district TEXT, village TEXT, lat REAL, long REAL,
        bts_room TEXT, link_type TEXT, site_grade TEXT, site_type TEXT,
        location TEXT, site_strategic TEXT, vendor TEXT
    )
"""

_VIP_SITE_CACHE_COLUMNS = {
    "site_code",
    "site_name",
    "status",
    "province",
    "district",
    "village",
    "lat",
    "long",
    "bts_room",
    "link_type",
    "site_grade",
    "site_type",
    "location",
    "site_strategic",
    "vendor",
}

# One row per Incident closed in the last 15 days, with enough detail
# for the "Incidents Closed – Week over Week" drilldown. See
# app/database/queries/incident_closed_trend.sql.
INCIDENT_CLOSED_TREND_CACHE_TABLES = ("incident_closed_trend",)

_INCIDENT_CLOSED_TREND_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        incident_id TEXT PRIMARY KEY, incident_numeric_id INTEGER, closed_at TEXT, incident_status TEXT,
        category TEXT, site_name TEXT, site_code TEXT,
        province TEXT, district TEXT, commune TEXT
    )
"""

_INCIDENT_CLOSED_TREND_CACHE_COLUMNS = {
    "incident_id",
    "incident_numeric_id",
    "closed_at",
    "incident_status",
    "category",
    "site_name",
    "site_code",
    "province",
    "district",
    "commune",
}

# One row per Incident created in the last 15 days, for the "Incident
# Volume – Week over Week" drilldown — same shape as
# incident_closed_trend above. See
# app/database/queries/incident_created_trend.sql.
INCIDENT_CREATED_TREND_CACHE_TABLES = ("incident_created_trend",)

_INCIDENT_CREATED_TREND_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        incident_id TEXT PRIMARY KEY, incident_numeric_id INTEGER, created_at TEXT, incident_status TEXT,
        category TEXT, severity TEXT, site_name TEXT, site_code TEXT, vendor TEXT,
        province TEXT, district TEXT, commune TEXT
    )
"""

_INCIDENT_CREATED_TREND_CACHE_COLUMNS = {
    "incident_id",
    "incident_numeric_id",
    "created_at",
    "incident_status",
    "category",
    "severity",
    "site_name",
    "site_code",
    "vendor",
    "province",
    "district",
    "commune",
}

# One row per (Site Down incident, Site) pair not yet Closed whose alarm
# hasn't cleared — the "Incident Site Down" card, also read directly by
# the Telegram Site Down alert instead of querying Postgres again. See
# app/services/incident/incident_sync_service.py.
INCIDENT_SITE_DOWN_CACHE_TABLES = ("incident_site_down",)

_INCIDENT_SITE_DOWN_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        incident_id TEXT, incident_numeric_id INTEGER, incident_status TEXT, wo_id TEXT,
        wo_numeric_id INTEGER, wo_created_at TEXT, wo_status TEXT, site_name TEXT, site_code TEXT,
        occurred_at TEXT, l1_noc_investigation_result TEXT, last_comments TEXT, source TEXT, nms TEXT,
        hub_site TEXT, site_grade TEXT, province TEXT, district TEXT, commune TEXT,
        PRIMARY KEY (incident_id, site_code)
    )
"""

_INCIDENT_SITE_DOWN_CACHE_COLUMNS = {
    "incident_id",
    "incident_numeric_id",
    "incident_status",
    "wo_id",
    "wo_numeric_id",
    "wo_created_at",
    "wo_status",
    "site_name",
    "site_code",
    "occurred_at",
    "l1_noc_investigation_result",
    "last_comments",
    "source",
    "nms",
    "hub_site",
    "site_grade",
    "province",
    "district",
    "commune",
}

# Per-incident Site Down detail for the last 30 days, with the real
# Root Cause Category Streamline assigns via the object_10 join — see
# incident_site_down_root_cause.sql. No PRIMARY KEY on incident_id: a
# small number of incidents carry more than one Root Cause Category
# (same fan-out as incident_root_cause.sql used to document before it
# was retired — see that history in incident_site_down_root_cause.sql's
# own header), so incident_id is deliberately NOT unique in this table.
INCIDENT_SITE_DOWN_ROOT_CAUSE_CACHE_TABLES = ("incident_site_down_root_cause",)

_INCIDENT_SITE_DOWN_ROOT_CAUSE_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        incident_id TEXT, site TEXT, actual_root_cause TEXT,
        root_cause_category TEXT, times INTEGER, occurred_at TEXT
    )
"""

_INCIDENT_SITE_DOWN_ROOT_CAUSE_CACHE_COLUMNS = {
    "incident_id",
    "site",
    "actual_root_cause",
    "root_cause_category",
    "times",
    "occurred_at",
}

# Worklog (free-text comments + system field-change entries, merged —
# see incident_worklog_by_ids.sql/incident_audit_log_by_ids.sql) for
# "Site Down by Age"'s own worklog popup — behind the bar chart's
# click-through. Deliberately scoped ONLY to currently-open Site Down
# incidents (the same set incident_site_down_cache already tracks), not
# the full worklog/audit history for every incident ever — keeps this
# table small and self-pruning: a resolved/closed incident's rows
# naturally disappear on the next sync cycle once it drops out of
# incident_site_down_cache, the same replace_all()-every-cycle pattern
# every other cache table here already uses. No PRIMARY KEY (an
# incident legitimately has several worklog entries).
INCIDENT_WORKLOG_CACHE_TABLES = ("incident_worklog",)

_INCIDENT_WORKLOG_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        incident_numeric_id INTEGER, incident_id TEXT, entry_text TEXT,
        created_at TEXT, created_by TEXT
    )
"""

_INCIDENT_WORKLOG_CACHE_COLUMNS = {
    "incident_numeric_id",
    "incident_id",
    "entry_text",
    "created_at",
    "created_by",
}

# One row per Site Down incident seen on the Telegram alert's last run —
# not filtered by ALERT_THRESHOLD_MIN, so this always reflects every
# current Site Down incident, not just the ones actually sent.
TELEGRAM_ALERT_CACHE_TABLES = ("telegram_alert_cache",)

_TELEGRAM_ALERT_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        incident_id TEXT, incident_status TEXT, wo_id TEXT,
        wo_created_at TEXT, wo_status TEXT, site_name TEXT, site_code TEXT,
        occurred_at TEXT, outage_min INTEGER, l1_noc_investigation_result TEXT, last_comments TEXT,
        nms TEXT, hub_site TEXT, site_grade TEXT, province TEXT, district TEXT, commune TEXT,
        PRIMARY KEY (incident_id, site_code)
    )
"""

_TELEGRAM_ALERT_CACHE_COLUMNS = {
    "incident_id",
    "incident_status",
    "wo_id",
    "wo_created_at",
    "wo_status",
    "site_name",
    "site_code",
    "occurred_at",
    "outage_min",
    "l1_noc_investigation_result",
    "last_comments",
    "nms",
    "hub_site",
    "site_grade",
    "province",
    "district",
    "commune",
}

# Response Time — Weekly Trend (Performance page), real data straight
# from object_322 (take_in_progress_at - issue_occurred_at), no join
# — see app/database/queries/incident_response_time_weekly.sql.
# ISO-week grouped, last 4 weeks; the most recent week is partial.
INCIDENT_RESPONSE_TIME_WEEKLY_CACHE_TABLES = ("incident_response_time_weekly",)

_INCIDENT_RESPONSE_TIME_WEEKLY_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        iso_week TEXT, category TEXT, incident_count INTEGER,
        min_minutes REAL, avg_minutes REAL, max_minutes REAL,
        PRIMARY KEY (iso_week, category)
    )
"""

_INCIDENT_RESPONSE_TIME_WEEKLY_CACHE_COLUMNS = {
    "iso_week",
    "category",
    "incident_count",
    "min_minutes",
    "avg_minutes",
    "max_minutes",
}

# Per-incident rows behind Response Time's duration-bucket breakdown —
# same window/filter as INCIDENT_RESPONSE_TIME_WEEKLY_CACHE_TABLES above,
# one row per incident instead of pre-aggregated, so a bucket can be
# clicked through to the real incidents behind it — see
# app/database/queries/incident_response_time_details.sql.
INCIDENT_RESPONSE_TIME_DETAILS_CACHE_TABLES = ("incident_response_time_details",)

_INCIDENT_RESPONSE_TIME_DETAILS_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        incident_id TEXT PRIMARY KEY, incident_numeric_id INTEGER, iso_week TEXT,
        category TEXT, occurred_at TEXT, took_in_progress_at TEXT, response_minutes REAL,
        creation_method TEXT
    )
"""

_INCIDENT_RESPONSE_TIME_DETAILS_CACHE_COLUMNS = {
    "incident_id",
    "incident_numeric_id",
    "iso_week",
    "category",
    "occurred_at",
    "took_in_progress_at",
    "response_minutes",
    "creation_method",
}

# Resolution Time — Weekly Trend (Performance page), real data straight
# from object_322 (resolved_at - issue_occurred_at), no join — see
# app/database/queries/incident_resolution_time_weekly.sql. Same shape
# as INCIDENT_RESPONSE_TIME_WEEKLY_CACHE_TABLES above.
INCIDENT_RESOLUTION_TIME_WEEKLY_CACHE_TABLES = ("incident_resolution_time_weekly",)

_INCIDENT_RESOLUTION_TIME_WEEKLY_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        iso_week TEXT, category TEXT, incident_count INTEGER,
        min_minutes REAL, avg_minutes REAL, max_minutes REAL,
        PRIMARY KEY (iso_week, category)
    )
"""

_INCIDENT_RESOLUTION_TIME_WEEKLY_CACHE_COLUMNS = {
    "iso_week",
    "category",
    "incident_count",
    "min_minutes",
    "avg_minutes",
    "max_minutes",
}

# Per-incident rows behind Resolution Time's duration-bucket breakdown —
# same window/filter as INCIDENT_RESOLUTION_TIME_WEEKLY_CACHE_TABLES
# above, one row per incident instead of pre-aggregated, so a bucket can
# be clicked through to the real incidents behind it — see
# app/database/queries/incident_resolution_time_details.sql.
INCIDENT_RESOLUTION_TIME_DETAILS_CACHE_TABLES = ("incident_resolution_time_details",)

_INCIDENT_RESOLUTION_TIME_DETAILS_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        incident_id TEXT PRIMARY KEY, incident_numeric_id INTEGER, iso_week TEXT,
        category TEXT, occurred_at TEXT, resolved_at TEXT, resolution_minutes REAL,
        creation_method TEXT
    )
"""

_INCIDENT_RESOLUTION_TIME_DETAILS_CACHE_COLUMNS = {
    "incident_id",
    "incident_numeric_id",
    "iso_week",
    "category",
    "occurred_at",
    "resolved_at",
    "resolution_minutes",
    "creation_method",
}

# SLA Compliance — Weekly Trends (Performance page), real data straight
# from object_322 (overdue_response / overdue), no join — see
# app/database/queries/incident_sla_compliance_weekly.sql.
# resolution_known_count is only incidents Streamline actually gave a
# verdict on (overdue IS NOT NULL) — see that query's header for why
# the blanks are excluded rather than guessed at from due_date.
INCIDENT_SLA_COMPLIANCE_WEEKLY_CACHE_TABLES = ("incident_sla_compliance_weekly",)

_INCIDENT_SLA_COMPLIANCE_WEEKLY_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        iso_week TEXT, category TEXT, priority TEXT, incident_count INTEGER,
        response_met_count INTEGER, response_sla_pct REAL,
        resolution_known_count INTEGER, resolution_met_count INTEGER,
        resolution_sla_pct REAL,
        PRIMARY KEY (iso_week, category, priority)
    )
"""

_INCIDENT_SLA_COMPLIANCE_WEEKLY_CACHE_COLUMNS = {
    "iso_week",
    "category",
    "priority",
    "incident_count",
    "response_met_count",
    "response_sla_pct",
    "resolution_known_count",
    "resolution_met_count",
    "resolution_sla_pct",
}

INCIDENT_SLA_COMPLIANCE_DETAILS_CACHE_TABLES = ("incident_sla_compliance_details",)

_INCIDENT_SLA_COMPLIANCE_DETAILS_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        incident_id TEXT PRIMARY KEY, incident_numeric_id INTEGER, iso_week TEXT,
        category TEXT, priority TEXT, support_level TEXT, site_grade TEXT,
        occurred_at TEXT, overdue_response INTEGER, overdue INTEGER
    )
"""

_INCIDENT_SLA_COMPLIANCE_DETAILS_CACHE_COLUMNS = {
    "incident_id",
    "incident_numeric_id",
    "iso_week",
    "category",
    "priority",
    "support_level",
    "site_grade",
    "occurred_at",
    "overdue_response",
    "overdue",
}

# SLA Compliance card's "View SLA Policy" reference table — object_327
# (a separate Streamline entity from Incident/object_322), the actual
# target/threshold rules behind object_322's own overdue/overdue_response
# verdicts. See sla_policy.sql — 80 rarely-changing rows, no incident_id
# involved, so no PRIMARY KEY beyond the rule's own id.
SLA_POLICY_CACHE_TABLES = ("sla_policy",)

_SLA_POLICY_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        id INTEGER PRIMARY KEY, category TEXT, priority TEXT,
        support_level TEXT, site_grade TEXT,
        response_time REAL, measure_response_time TEXT,
        resolution_time REAL, measure_resolution_time TEXT
    )
"""

_SLA_POLICY_CACHE_COLUMNS = {
    "id",
    "category",
    "priority",
    "support_level",
    "site_grade",
    "response_time",
    "measure_response_time",
    "resolution_time",
    "measure_resolution_time",
}

# Site-Down Duration — Weekly Trend (Performance page section on the
# Overall Dashboard), real data from object_322 — one row per (closed
# Site Down incident, Site) pair in the last 30 days — a multi-site
# incident produces one row per site (see
# incident_site_down_duration_weekly.sql's LATERAL UNNEST), so
# PRIMARY KEY is the pair, not incident_id alone, same as
# incident_by_status/incident_site_down above. Has both
# issue_occurred_at and resolved_at so duration can be bucketed
# (<4h/4-8h/8-12h/12-24h/>24h) per week in
# IncidentService.get_site_down_duration_trend().
INCIDENT_SITE_DOWN_DURATION_WEEKLY_CACHE_TABLES = ("incident_site_down_duration_weekly",)

_INCIDENT_SITE_DOWN_DURATION_WEEKLY_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        incident_id TEXT, incident_numeric_id INTEGER, site TEXT, site_code TEXT,
        occurred_at TEXT, resolved_at TEXT, closed_at TEXT,
        PRIMARY KEY (incident_id, site_code)
    )
"""

_INCIDENT_SITE_DOWN_DURATION_WEEKLY_CACHE_COLUMNS = {
    "incident_id",
    "incident_numeric_id",
    "site",
    "site_code",
    "occurred_at",
    "resolved_at",
    "closed_at",
}

# Same shape as incident_site_down_duration_weekly above, minus the
# site_down-only scope — every category, for the "By Category —
# <Weekday>" popup's duration breakdown (Incident Volume card). See
# IncidentService._duration_weekly_rows()/_bucket_duration_by_created_
# weekday_and_category().
INCIDENT_DURATION_WEEKLY_CACHE_TABLES = ("incident_duration_weekly",)

_INCIDENT_DURATION_WEEKLY_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        incident_id TEXT PRIMARY KEY, incident_numeric_id INTEGER, category TEXT, site TEXT, site_code TEXT,
        occurred_at TEXT, resolved_at TEXT, closed_at TEXT
    )
"""

_INCIDENT_DURATION_WEEKLY_CACHE_COLUMNS = {
    "incident_id",
    "incident_numeric_id",
    "category",
    "site",
    "site_code",
    "occurred_at",
    "resolved_at",
    "closed_at",
}

# Same "last-run snapshot" role as telegram_alert_cache, for the INC-WO
# Site Down Telegram alert — its own table since replace_all() wipes the
# whole table each run, and this alert's row shape differs
# (wo_created_at instead of occurred_at, fault_description instead of
# l1_noc_investigation_result/last_comments).
TELEGRAM_INC_WO_ALERT_CACHE_TABLES = ("telegram_inc_wo_alert_cache",)

_TELEGRAM_INC_WO_ALERT_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        incident_id TEXT, incident_status TEXT, wo_id TEXT PRIMARY KEY,
        wo_created_at TEXT, wo_status TEXT, site_name TEXT, site_code TEXT,
        outage_min INTEGER, fault_description TEXT,
        nms TEXT, hub_site TEXT, site_grade TEXT, province TEXT, district TEXT, commune TEXT
    )
"""

_TELEGRAM_INC_WO_ALERT_CACHE_COLUMNS = {
    "incident_id",
    "incident_status",
    "wo_id",
    "wo_created_at",
    "wo_status",
    "site_name",
    "site_code",
    "outage_min",
    "fault_description",
    "nms",
    "hub_site",
    "site_grade",
    "province",
    "district",
    "commune",
}

# Same "last-run snapshot" role as telegram_inc_wo_alert_cache, for the
# Category Power alert — its own table so replace_all() can't overwrite
# another alert's snapshot.
TELEGRAM_INC_WO_POWER_ALERT_CACHE_TABLES = ("telegram_inc_wo_power_alert_cache",)

_TELEGRAM_INC_WO_POWER_ALERT_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        incident_id TEXT, incident_status TEXT, wo_id TEXT PRIMARY KEY,
        wo_created_at TEXT, wo_status TEXT, site_name TEXT, site_code TEXT,
        outage_min INTEGER, fault_description TEXT,
        nms TEXT, hub_site TEXT, site_grade TEXT, province TEXT, district TEXT, commune TEXT
    )
"""

_TELEGRAM_INC_WO_POWER_ALERT_CACHE_COLUMNS = {
    "incident_id",
    "incident_status",
    "wo_id",
    "wo_created_at",
    "wo_status",
    "site_name",
    "site_code",
    "outage_min",
    "fault_description",
    "nms",
    "hub_site",
    "site_grade",
    "province",
    "district",
    "commune",
}

# Same "last-run snapshot" role, for the General alert — its own table
# so replace_all() can't overwrite another alert's snapshot.
TELEGRAM_INC_WO_GENERAL_ALERT_CACHE_TABLES = ("telegram_inc_wo_general_alert_cache",)

_TELEGRAM_INC_WO_GENERAL_ALERT_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        incident_id TEXT, incident_status TEXT, wo_id TEXT PRIMARY KEY,
        wo_created_at TEXT, wo_status TEXT, site_name TEXT, site_code TEXT,
        outage_min INTEGER, fault_description TEXT,
        nms TEXT, hub_site TEXT, site_grade TEXT, province TEXT, district TEXT, commune TEXT
    )
"""

_TELEGRAM_INC_WO_GENERAL_ALERT_CACHE_COLUMNS = {
    "incident_id",
    "incident_status",
    "wo_id",
    "wo_created_at",
    "wo_status",
    "site_name",
    "site_code",
    "outage_min",
    "fault_description",
    "nms",
    "hub_site",
    "site_grade",
    "province",
    "district",
    "commune",
}

# One row per POP (noc.TBL_POP on MSSQL) — same table alarms.sql joins
# against for pop_name/pop_code/province. See
# app/database/queries/pop.sql.
POP_CACHE_TABLES = ("pop_cache",)

_POP_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        id TEXT PRIMARY KEY, name TEXT, code TEXT, owner TEXT, owner_code TEXT,
        lat REAL, long REAL, province TEXT, district TEXT, commune TEXT,
        location TEXT, type TEXT, network_type TEXT, con_name TEXT, con_num TEXT,
        pre_owner TEXT, pro_owner TEXT, remark TEXT, is_removed TEXT, cd TEXT, md TEXT,
        aircon TEXT, edc TEXT, dg TEXT, solar TEXT, rectifier TEXT, inverter TEXT,
        ups TEXT, colocated TEXT, active TEXT, cus TEXT, ncode TEXT, backup_status TEXT
    )
"""

_POP_CACHE_COLUMNS = {
    "id",
    "name",
    "code",
    "owner",
    "owner_code",
    "lat",
    "long",
    "province",
    "district",
    "commune",
    "location",
    "type",
    "network_type",
    "con_name",
    "con_num",
    "pre_owner",
    "pro_owner",
    "remark",
    "is_removed",
    "cd",
    "md",
    "aircon",
    "edc",
    "dg",
    "solar",
    "rectifier",
    "inverter",
    "ups",
    "colocated",
    "active",
    "cus",
    "ncode",
    "backup_status",
}

# One row per On-Air site from MSSQL (TBL_SITE joined to TBL_NE for
# VENDOR) — independent from Postgres's site_cache above. See
# app/database/queries/mssql_site.sql.
MSSQL_SITE_ONAIR_CACHE_TABLES = ("mssql_site_onair",)

_MSSQL_SITE_ONAIR_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        site_code TEXT PRIMARY KEY, site_name TEXT, status TEXT,
        province TEXT, district TEXT, village TEXT, lat REAL, long REAL,
        bts_room TEXT, link_type TEXT, site_grade TEXT, site_type TEXT,
        location TEXT, vendor TEXT
    )
"""

_MSSQL_SITE_ONAIR_CACHE_COLUMNS = {
    "site_code",
    "site_name",
    "status",
    "province",
    "district",
    "village",
    "lat",
    "long",
    "bts_room",
    "link_type",
    "site_grade",
    "site_type",
    "location",
    "vendor",
}

# One row per active NE/connectivity alarm (object_138) — the broader
# VVIP/Mentor/RAN alarm set, not just Main Failure. Site Code is
# resolved locally (app/utils/get_processed_site.py), then Site Name
# against site_cache. See app/services/ape_alarm/ape_alarm_sync_service.py.
#
# alarm_numeric_id/alarm_id mirror Streamline's own "ID"/"Alarm ID"
# fields — cached so every service sharing this cache can display/link
# them without a second query.
APE_ALARM_CACHE_TABLES = ("ape_alarm",)

_APE_ALARM_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        alarm_numeric_id INTEGER, alarm_id TEXT,
        occurred_at TEXT, event_name TEXT, additional_info TEXT,
        nms TEXT, technology TEXT, site_code TEXT, site_name TEXT, occurrence_count INTEGER
    )
"""

_APE_ALARM_CACHE_COLUMNS = {
    "alarm_numeric_id",
    "alarm_id",
    "occurred_at",
    "event_name",
    "additional_info",
    "nms",
    "technology",
    "site_code",
    "site_name",
    "occurrence_count",
}

# One row per active alarm at a VIP/VVIP site — filtered locally from
# the already-synced ape_alarm cache (via site_cache.site_strategic_type),
# not a second Postgres query. See app/services/vip/vip_alarm_sync_service.py.
VIP_ALARM_CACHE_TABLES = ("vip_alarm",)

_VIP_ALARM_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        alarm_numeric_id INTEGER, alarm_id TEXT,
        occurred_at TEXT, event_name TEXT, additional_info TEXT,
        nms TEXT, technology TEXT, site_code TEXT, site_name TEXT, site_strategic_type TEXT,
        occurrence_count INTEGER
    )
"""

_VIP_ALARM_CACHE_COLUMNS = {
    "alarm_numeric_id",
    "alarm_id",
    "occurred_at",
    "event_name",
    "additional_info",
    "nms",
    "technology",
    "site_code",
    "site_name",
    "site_strategic_type",
    "occurrence_count",
}

# Mirrors Postgres's site_lookup_mv (sran_id/nodeb_id/bts_id ->
# site_name) — the lookup table get_processed_site() used to query
# internally. See app/utils/get_processed_site.py.
SITE_LOOKUP_CACHE_TABLES = ("site_lookup_cache",)

_SITE_LOOKUP_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        sran_id INTEGER, nodeb_id INTEGER, bts_id INTEGER, site_name TEXT
    )
"""

_SITE_LOOKUP_CACHE_COLUMNS = {"sran_id", "nodeb_id", "bts_id", "site_name"}

# One row per (site, technology) pair a site has an NE for (object_227,
# distinct). technology is always '2g'/'3g'/'4g'/'5g'. Used to tell
# whether every technology a site has is currently down, not just one.
# See app/services/alarm_site_down/alarm_completely_site_down_service.py.
SITE_TECHNOLOGY_CACHE_TABLES = ("site_technology_cache",)

_SITE_TECHNOLOGY_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        site_code TEXT, technology TEXT,
        PRIMARY KEY (site_code, technology)
    )
"""

_SITE_TECHNOLOGY_CACHE_COLUMNS = {"site_code", "technology"}

# One row per site with an NE (object_227) — the site's NMS vendor
# code, resolved once here instead of recomputed in 6 other queries.
# See app/services/site/site_sync_service.py's sync_ne_nms().
NE_NMS_LOOKUP_CACHE_TABLES = ("ne_nms_lookup_cache",)

_NE_NMS_LOOKUP_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        site_code TEXT PRIMARY KEY, nms_code TEXT
    )
"""

_NE_NMS_LOOKUP_CACHE_COLUMNS = {"site_code", "nms_code"}

# One row per site with an object_160.actual_ran_vendor value — a
# site-level "who actually runs this site's RAN" field, separate from
# ne_nms_lookup_cache. Only a few codes are confirmed (see
# app/utils/nms.py's ACTUAL_RAN_VENDOR_TO_NMS_CODE); the rest are
# unconfirmed. See app/services/site/site_sync_service.py's sync_ran_vendor().
SITE_RAN_VENDOR_CACHE_TABLES = ("site_ran_vendor_cache",)

_SITE_RAN_VENDOR_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        site_code TEXT PRIMARY KEY, actual_ran_vendor INTEGER
    )
"""

_SITE_RAN_VENDOR_CACHE_COLUMNS = {"site_code", "actual_ran_vendor"}

# Mirrors object_170 ("Counterparty") — the platform's general
# business-partner catalog (vendors, brands, site owners, energy
# suppliers, etc — see its `type` column). See
# app/database/queries/counterparty.sql and
# app/services/site/site_sync_service.py's sync_counterparty().
COUNTERPARTY_CACHE_TABLES = ("counterparty_cache",)

_COUNTERPARTY_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        id INTEGER PRIMARY KEY, name TEXT, type TEXT
    )
"""

_COUNTERPARTY_CACHE_COLUMNS = {"id", "name", "type"}

# One row per (Partner, Contact) pair from MSSQL's TBL_PARTNER /
# TBL_PARTNER_CONTACT ONLY — TBL_PARTNER_CIRCUIT is not used anywhere in
# this app. remark/contact_role are TBL_PARTNER_CONTACT.Remark/ContactRole
# (per-contact) — NOT TBL_PARTNER.Remark, a separate unused column. See
# app/services/partner_contact/partner_contact_sync_service.py.
PARTNER_CONTACT_CACHE_TABLES = ("partner_contact_cache",)

_PARTNER_CONTACT_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        partner_id TEXT, contact_id TEXT,
        partner_name TEXT, partner_type TEXT, domain TEXT,
        escalation_level TEXT, escalation_matrix TEXT,
        contact_name TEXT, contact_role TEXT,
        phone_number TEXT, email TEXT,
        remark TEXT,
        created_by TEXT, created_at TEXT, updated_by TEXT, updated_at TEXT
    )
"""

_PARTNER_CONTACT_CACHE_COLUMNS = {
    "partner_id",
    "contact_id",
    "partner_name",
    "partner_type",
    "domain",
    "escalation_level",
    "escalation_matrix",
    "contact_name",
    "contact_role",
    "phone_number",
    "email",
    "created_by",
    "created_at",
    "updated_by",
    "updated_at",
    "remark",
}

# (cache table names, CREATE TABLE template, expected columns) — used by
# init_cache_db() to create each group and drop-and-recreate any table
# whose columns are stale.
_CACHE_DEFINITIONS = (
    (ALARM_CACHE_TABLES, _ALARM_TABLE_SCHEMA, _ALARM_CACHE_COLUMNS),
    (SITE_CACHE_TABLES, _SITE_TABLE_SCHEMA, _SITE_CACHE_COLUMNS),
    (INCIDENT_STATUS_CACHE_TABLES, _INCIDENT_STATUS_TABLE_SCHEMA, _INCIDENT_STATUS_CACHE_COLUMNS),
    (
        VIP_INCIDENT_STATUS_CACHE_TABLES,
        _VIP_INCIDENT_STATUS_TABLE_SCHEMA,
        _VIP_INCIDENT_STATUS_CACHE_COLUMNS,
    ),
    (INC_WO_STATUS_CACHE_TABLES, _INC_WO_STATUS_TABLE_SCHEMA, _INC_WO_STATUS_CACHE_COLUMNS),
    (INC_WO_RESOLVED_CACHE_TABLES, _INC_WO_RESOLVED_TABLE_SCHEMA, _INC_WO_RESOLVED_CACHE_COLUMNS),
    (VIP_SITE_CACHE_TABLES, _VIP_SITE_TABLE_SCHEMA, _VIP_SITE_CACHE_COLUMNS),
    (
        INCIDENT_CLOSED_TREND_CACHE_TABLES,
        _INCIDENT_CLOSED_TREND_TABLE_SCHEMA,
        _INCIDENT_CLOSED_TREND_CACHE_COLUMNS,
    ),
    (
        INCIDENT_CREATED_TREND_CACHE_TABLES,
        _INCIDENT_CREATED_TREND_TABLE_SCHEMA,
        _INCIDENT_CREATED_TREND_CACHE_COLUMNS,
    ),
    (POP_CACHE_TABLES, _POP_TABLE_SCHEMA, _POP_CACHE_COLUMNS),
    (
        MSSQL_SITE_ONAIR_CACHE_TABLES,
        _MSSQL_SITE_ONAIR_TABLE_SCHEMA,
        _MSSQL_SITE_ONAIR_CACHE_COLUMNS,
    ),
    (
        INCIDENT_SITE_DOWN_CACHE_TABLES,
        _INCIDENT_SITE_DOWN_TABLE_SCHEMA,
        _INCIDENT_SITE_DOWN_CACHE_COLUMNS,
    ),
    (
        INCIDENT_SITE_DOWN_ROOT_CAUSE_CACHE_TABLES,
        _INCIDENT_SITE_DOWN_ROOT_CAUSE_TABLE_SCHEMA,
        _INCIDENT_SITE_DOWN_ROOT_CAUSE_CACHE_COLUMNS,
    ),
    (
        INCIDENT_WORKLOG_CACHE_TABLES,
        _INCIDENT_WORKLOG_TABLE_SCHEMA,
        _INCIDENT_WORKLOG_CACHE_COLUMNS,
    ),
    (
        INCIDENT_RESPONSE_TIME_WEEKLY_CACHE_TABLES,
        _INCIDENT_RESPONSE_TIME_WEEKLY_TABLE_SCHEMA,
        _INCIDENT_RESPONSE_TIME_WEEKLY_CACHE_COLUMNS,
    ),
    (
        INCIDENT_RESPONSE_TIME_DETAILS_CACHE_TABLES,
        _INCIDENT_RESPONSE_TIME_DETAILS_TABLE_SCHEMA,
        _INCIDENT_RESPONSE_TIME_DETAILS_CACHE_COLUMNS,
    ),
    (
        INCIDENT_RESOLUTION_TIME_WEEKLY_CACHE_TABLES,
        _INCIDENT_RESOLUTION_TIME_WEEKLY_TABLE_SCHEMA,
        _INCIDENT_RESOLUTION_TIME_WEEKLY_CACHE_COLUMNS,
    ),
    (
        INCIDENT_RESOLUTION_TIME_DETAILS_CACHE_TABLES,
        _INCIDENT_RESOLUTION_TIME_DETAILS_TABLE_SCHEMA,
        _INCIDENT_RESOLUTION_TIME_DETAILS_CACHE_COLUMNS,
    ),
    (
        INCIDENT_SLA_COMPLIANCE_WEEKLY_CACHE_TABLES,
        _INCIDENT_SLA_COMPLIANCE_WEEKLY_TABLE_SCHEMA,
        _INCIDENT_SLA_COMPLIANCE_WEEKLY_CACHE_COLUMNS,
    ),
    (
        INCIDENT_SLA_COMPLIANCE_DETAILS_CACHE_TABLES,
        _INCIDENT_SLA_COMPLIANCE_DETAILS_TABLE_SCHEMA,
        _INCIDENT_SLA_COMPLIANCE_DETAILS_CACHE_COLUMNS,
    ),
    (
        SLA_POLICY_CACHE_TABLES,
        _SLA_POLICY_TABLE_SCHEMA,
        _SLA_POLICY_CACHE_COLUMNS,
    ),
    (
        INCIDENT_SITE_DOWN_DURATION_WEEKLY_CACHE_TABLES,
        _INCIDENT_SITE_DOWN_DURATION_WEEKLY_TABLE_SCHEMA,
        _INCIDENT_SITE_DOWN_DURATION_WEEKLY_CACHE_COLUMNS,
    ),
    (
        INCIDENT_DURATION_WEEKLY_CACHE_TABLES,
        _INCIDENT_DURATION_WEEKLY_TABLE_SCHEMA,
        _INCIDENT_DURATION_WEEKLY_CACHE_COLUMNS,
    ),
    (TELEGRAM_ALERT_CACHE_TABLES, _TELEGRAM_ALERT_TABLE_SCHEMA, _TELEGRAM_ALERT_CACHE_COLUMNS),
    (
        TELEGRAM_INC_WO_ALERT_CACHE_TABLES,
        _TELEGRAM_INC_WO_ALERT_TABLE_SCHEMA,
        _TELEGRAM_INC_WO_ALERT_CACHE_COLUMNS,
    ),
    (
        TELEGRAM_INC_WO_POWER_ALERT_CACHE_TABLES,
        _TELEGRAM_INC_WO_POWER_ALERT_TABLE_SCHEMA,
        _TELEGRAM_INC_WO_POWER_ALERT_CACHE_COLUMNS,
    ),
    (
        TELEGRAM_INC_WO_GENERAL_ALERT_CACHE_TABLES,
        _TELEGRAM_INC_WO_GENERAL_ALERT_TABLE_SCHEMA,
        _TELEGRAM_INC_WO_GENERAL_ALERT_CACHE_COLUMNS,
    ),
    (APE_ALARM_CACHE_TABLES, _APE_ALARM_TABLE_SCHEMA, _APE_ALARM_CACHE_COLUMNS),
    (VIP_ALARM_CACHE_TABLES, _VIP_ALARM_TABLE_SCHEMA, _VIP_ALARM_CACHE_COLUMNS),
    (SITE_LOOKUP_CACHE_TABLES, _SITE_LOOKUP_TABLE_SCHEMA, _SITE_LOOKUP_CACHE_COLUMNS),
    (SITE_TECHNOLOGY_CACHE_TABLES, _SITE_TECHNOLOGY_TABLE_SCHEMA, _SITE_TECHNOLOGY_CACHE_COLUMNS),
    (NE_NMS_LOOKUP_CACHE_TABLES, _NE_NMS_LOOKUP_TABLE_SCHEMA, _NE_NMS_LOOKUP_CACHE_COLUMNS),
    (SITE_RAN_VENDOR_CACHE_TABLES, _SITE_RAN_VENDOR_TABLE_SCHEMA, _SITE_RAN_VENDOR_CACHE_COLUMNS),
    (COUNTERPARTY_CACHE_TABLES, _COUNTERPARTY_TABLE_SCHEMA, _COUNTERPARTY_CACHE_COLUMNS),
    (
        PARTNER_CONTACT_CACHE_TABLES,
        _PARTNER_CONTACT_TABLE_SCHEMA,
        _PARTNER_CONTACT_CACHE_COLUMNS,
    ),
    (
        CONGESTION_FLAP_CACHE_TABLES,
        _CONGESTION_FLAP_TABLE_SCHEMA,
        _CONGESTION_FLAP_CACHE_COLUMNS,
    ),
)

# Tables no longer synced by anything — dropped on startup so an
# existing localstorage.db doesn't keep stale data around.
_RETIRED_TABLES = (
    "incident_cache",
    "winauth_registered_user",
    "incident_closed_site",
    "incident_wo_site",
    "vip_customer_complaint",
    "vip_incident_alarm",
)


def db_path() -> Path:
    return Path(current_app.instance_path) / "localstorage.db"


def get_cache_conn() -> sqlite3.Connection:
    """WAL mode avoids "database is locked" errors from concurrent
    background sync threads (the default rollback-journal mode locks the
    whole file during a write)."""
    conn = sqlite3.connect(db_path(), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def cache_conn_scope():
    """A cache connection reused for the rest of the current request
    (via `g`) instead of reopened on every call — a page load can make
    15-20 separate cache reads. Falls back to a one-off connection
    outside a request context (background sync)."""
    if not has_request_context():
        conn = get_cache_conn()
        try:
            yield conn
        finally:
            conn.close()
        return

    if "cache_conn" not in g:
        g.cache_conn = get_cache_conn()
    yield g.cache_conn


def close_request_cache_conn(exception=None):
    """Teardown hook (app/__init__.py) — closes the connection
    cache_conn_scope() cached on `g` for this request, if any."""
    conn = g.pop("cache_conn", None)
    if conn is not None:
        conn.close()


def _expected_pk_columns(schema):
    """Primary key column(s) a CREATE TABLE schema declares, from either
    a trailing PRIMARY KEY(...) clause or an inline column definition —
    used by init_cache_db() to detect a primary-key change even when the
    column names are unchanged."""
    composite = re.search(r"PRIMARY KEY\s*\(([^)]+)\)", schema, re.IGNORECASE)
    if composite:
        return {c.strip() for c in composite.group(1).split(",")}
    inline = re.search(r"(\w+)\s+\w+\s+PRIMARY KEY", schema, re.IGNORECASE)
    return {inline.group(1)} if inline else set()


def init_cache_db() -> None:
    """Create the cache tables if they don't exist. Idempotent, safe on
    every startup. These are pure caches, so a schema change just drops
    and recreates the table."""
    conn = get_cache_conn()
    try:
        existing = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        for table in _RETIRED_TABLES:
            if table in existing:
                conn.execute(f"DROP TABLE {table}")
        for tables, schema, expected_columns in _CACHE_DEFINITIONS:
            expected_pk = _expected_pk_columns(schema)
            for table in tables:
                if table in existing:
                    info = conn.execute(f"PRAGMA table_info({table})").fetchall()
                    cols = {r[1] for r in info}
                    pk = {r[1] for r in info if r[5]}
                    if cols != expected_columns or pk != expected_pk:
                        conn.execute(f"DROP TABLE {table}")
                conn.execute(schema.format(table=table))
                # congestion_history_cache is the one table in this whole
                # file big enough (~9-10k rows, 4 weeks of HISTORICAL rows,
                # not just active alarms) for an unindexed device_name scan
                # to actually show up — a per-device drilldown (Top
                # Congestion Devices card) fetching all ~9-10k rows just to
                # keep one device's few-hundred-to-few-thousand measured
                # ~100-450ms per request before this index. Added for every
                # table with a device_name column (not just that one) since
                # checking column membership is simpler than naming tables —
                # harmless on the other 4 (isp_pop/eze/tct/it_node), which
                # are tiny active-only tables where this never mattered.
                if "device_name" in expected_columns:
                    conn.execute(
                        f"CREATE INDEX IF NOT EXISTS idx_{table}_device_name ON {table}(device_name)"
                    )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS sync_meta ("
            "table_name TEXT PRIMARY KEY, last_synced_at TEXT)"
        )
        # mentor_sites holds user-entered site codes (app/routes/mentor.py),
        # not synced data — excluded from the drop-and-recreate loop above
        # since it must never be dropped automatically.
        conn.execute(
            "CREATE TABLE IF NOT EXISTS mentor_sites ("
            "site_code TEXT PRIMARY KEY, added_at TEXT, source TEXT)"
        )
        # incident_reports holds user-authored Incident Reports (Incident
        # Report page) — same "never auto-dropped" reasoning as
        # mentor_sites above, just with real columns instead of a single
        # site_code since a report has many fields. chronology_events_json
        # is a JSON-encoded list of {"time", "description"} — the
        # Chronology of Events section is a variable-length list per
        # report, not a fixed set of columns.
        conn.execute(
            "CREATE TABLE IF NOT EXISTS incident_reports ("
            "id TEXT PRIMARY KEY, file_name TEXT, incident_raised_by TEXT, incident_received_by TEXT, "
            "reported_date TEXT, service_disruption TEXT, incident_date TEXT, "
            "report_time TEXT, incident_number TEXT, incident_category TEXT, "
            "customers_impacted TEXT, duration_of_interruption TEXT, time_issue TEXT, "
            "raise_time TEXT, response_time TEXT, restored_time TEXT, "
            "details_date_and_time TEXT, time_of_complaint TEXT, issue_reported TEXT, "
            "actions_taken_summary TEXT, chronology_events_json TEXT, "
            "cause_of_outage TEXT, fault_gps_location TEXT, resolution TEXT, "
            "permanent_fixed TEXT, status TEXT, created_at TEXT, updated_at TEXT)"
        )
        # document_title added after incident_reports already shipped —
        # CREATE TABLE IF NOT EXISTS above is a no-op once the table
        # exists, and this table is deliberately never dropped-and-
        # recreated (unlike every cache table above) since it holds real
        # user-authored reports, not just synced data. ALTER TABLE ADD
        # COLUMN is the only way to add a new field here without losing
        # every report already saved.
        existing_report_cols = {r[1] for r in conn.execute("PRAGMA table_info(incident_reports)").fetchall()}
        if "document_title" not in existing_report_cols:
            conn.execute("ALTER TABLE incident_reports ADD COLUMN document_title TEXT")
        # "Add Second Fault" — most reports have exactly one Fault
        # Analysis & Resolution (the original 4 columns above), but a
        # real incident can turn out to have two distinct root causes
        # discovered in sequence (confirmed against a real Telcotech
        # report: first blamed on a submarine cable partner's
        # maintenance, later found to also involve a separate fiber
        # cut) — Telcotech's own template handles this with a second
        # page repeating the same 5 fields for the 2nd cause, plus two
        # sections this app didn't have before: Improvement/Preventive
        # Plan (a variable-length list, same "_json" convention as
        # chronology_events_json) and Picture Reference (photos,
        # base64-encoded into their own JSON list rather than saved to
        # disk — this app has no upload-to-disk path anywhere yet, and
        # a NOC report's occasional handful of photos doesn't justify
        # building one). has_second_fault is the toggle ("1" or "") the
        # web form's "Add Second Fault" button sets — page 2 (and the
        # 5 "_2" fields' own validation) only applies once it's set.
        for column in (
            "issued_time",
            "has_second_fault",
            "cause_of_outage_2",
            "fault_gps_location_2",
            "issued_time_2",
            "resolution_2",
            "permanent_fixed_2",
            "improvement_plan_json",
            "picture_references_json",
        ):
            if column not in existing_report_cols:
                conn.execute(f"ALTER TABLE incident_reports ADD COLUMN {column} TEXT")
        # site_down_24h_alert_cache — the Site Down 24h Teams alert's own
        # dedup ledger (app/services/incident/site_down_24h_alert_service.py).
        # Deliberately NOT in _CACHE_DEFINITIONS above: every table there is a
        # disposable mirror of live Postgres/MSSQL data, safe to drop and
        # recreate on any schema change or resync. This one is the opposite —
        # it's this app's OWN memory of "have I already posted about this
        # incident", built up one row at a time as alerts actually get sent,
        # same "never auto-dropped" reasoning as mentor_sites/incident_reports
        # above. down_alert_sent_at/restore_alert_sent_at are separately
        # nullable timestamps, not a single status flag, so one row carries
        # the full history of both posts for an incident that's fully done.
        conn.execute(
            "CREATE TABLE IF NOT EXISTS site_down_24h_alert_cache ("
            "incident_id TEXT PRIMARY KEY, site_code TEXT, incident_ref TEXT, "
            "down_alert_sent_at TEXT, restore_alert_sent_at TEXT)"
        )
        # incident_ref added after this table already shipped — same
        # ALTER-TABLE-ADD-COLUMN reasoning as incident_reports'
        # document_title above (CREATE TABLE IF NOT EXISTS is a no-op
        # once the table exists, and this table is never dropped-and-
        # recreated like the mirror tables in _CACHE_DEFINITIONS are).
        existing_ledger_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(site_down_24h_alert_cache)").fetchall()
        }
        if "incident_ref" not in existing_ledger_cols:
            conn.execute("ALTER TABLE site_down_24h_alert_cache ADD COLUMN incident_ref TEXT")
        conn.commit()
    finally:
        conn.close()
