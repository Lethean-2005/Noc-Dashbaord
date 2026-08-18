"""Local SQLite cache — instance/localstorage.db.

Mirrors the MSSQL alarm feed locally so request-time reads (dashboard cards,
drilldown tables, CSV export) never hit MSSQL directly; app/services/alarm/alarm_scheduler.py
keeps it in sync in the background. Same role as Autonoc-Dashboard's
app/cache/localstorage.db, one file per project.
"""

import re
import sqlite3
from pathlib import Path

from flask import current_app

# One row per active alarm, normalized to the same shape regardless of which
# MSSQL query it came from (see app/services/alarm/alarm_sync_service.py).
# it_node_alarm_cache is the "IT NODE" card on the Custom Dashboard
# (reports/index.html) — same shape, device_name/ip_address/pop_name/
# pop_code/province just stay blank since IT_NODE alarms carry none of that.
ALARM_CACHE_TABLES = (
    "isp_pop_alarm_cache",
    "eze_alarm_cache",
    "tct_alarm_cache",
    "it_node_alarm_cache",
)

_ALARM_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        id TEXT, alarm TEXT, alarm_name TEXT, device_name TEXT, ip_address TEXT, pop_name TEXT,
        pop_code TEXT, province TEXT, down_time TEXT, root_cause TEXT, rtid TEXT,
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
    "down_time",
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

# One row per Site (object_160 on PostgreSQL), curated down to the columns
# the dashboard actually needs — see app/services/site/site_sync_service.py.
# Province/District/Commune/Village store resolved names (TEXT), not the
# raw object_162/164/166/168 FK ids; physical_location_name/_address come
# from a join to object_308 — see app/database/queries/site_cache.sql.
SITE_CACHE_TABLES = ("site_cache",)

_SITE_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        id INTEGER PRIMARY KEY, name TEXT, status TEXT, type TEXT,
        site_grade TEXT, fra_site_name TEXT, standard_code TEXT, site_priority TEXT,
        site_strategic_type TEXT,
        province TEXT, district TEXT, commune TEXT, village TEXT,
        physical_location INTEGER, physical_location_name TEXT,
        physical_location_address TEXT, p_lat REAL, p_lon REAL, hub_site TEXT
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
}

# One row per (Incident, Site) pair currently in 'new' or 'in_progress'
# status — the full joined drilldown detail (Site/INC-WO/Province/District/
# Commune/NMS) behind every Incident-column badge. A multi-site incident is
# more than one row here, one per site, sharing the same incident_id — see
# app/database/queries/incident_by_status.sql for the join logic and
# app/services/incident/incident_sync_service.py for the sync.
#
# responsible_team/support_level are the WO's own fields, not the parent
# Incident's — also used by MentorSiteService's enrichment.
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

# Same shape as incident_by_status above, but scoped to only VIP/VVIP
# sites and to status != 'closed' (so a Resolved incident still shows).
# Kept as its own table rather than widening incident_by_status itself,
# which is shared by IncidentService/MentorSiteService and has no
# pagination — widening it directly caused a real outage. Scoping to just
# VIP/VVIP sites keeps this table small even with full Resolved history.
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

# One row per INC-WO not yet 'closed' — the full joined drilldown detail
# (Site/Incident/NMS/...) behind every INC-WO-column badge. See
# app/database/queries/inc_wo_by_status.sql for the join logic and
# app/services/incident/incident_sync_service.py for the sync. wo_id can be NULL for
# a freshly-created 'new' work order (not yet assigned a real id) — SQLite
# allows multiple NULLs in a PRIMARY KEY/UNIQUE column, same as standard SQL.
#
# inc_wo_site_down and inc_wo_category_power share this exact same shape —
# each narrowed to one work order category (site_down / power) not yet
# resolved/closed. inc_wo_site_down backs the "INC-WO Site Down" card;
# inc_wo_category_power has no dashboard card, feeding only
# telegram_inc_wo_power_alert.py.
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

# One row per INC-WO that's Resolved while its parent Incident is still
# In-Progress overall — behind the "INC-WO Resolved" card on the Custom
# Dashboard (reports/index.html). Same shape as inc_wo_by_status/
# inc_wo_site_down plus incident_status (this query's INNER JOIN condition
# includes the parent Incident's own status). See
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

# One row per VIP/VVIP Site (SITE_INFO on MSSQL) — see
# app/database/queries/vip_site_cache.sql and app/services/vip/vip_site_sync_service.py
# for the sync. `id` (a GUID) is used as the primary key since SITE_CODE and
# BTS_NAME both have real duplicates in this table (multiple sectors/
# technologies can share the same physical site).
VIP_SITE_CACHE_TABLES = ("vip_site_cache",)

_VIP_SITE_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        id TEXT PRIMARY KEY, site_code TEXT, site_name TEXT, bts_name TEXT, vip TEXT,
        province TEXT, district TEXT, commune TEXT, village TEXT, location TEXT,
        site_grade TEXT, on_air TEXT, product TEXT, tech TEXT, site_id TEXT,
        lat REAL, long REAL
    )
"""

_VIP_SITE_CACHE_COLUMNS = {
    "id",
    "site_code",
    "site_name",
    "bts_name",
    "vip",
    "province",
    "district",
    "commune",
    "village",
    "location",
    "site_grade",
    "on_air",
    "product",
    "tech",
    "site_id",
    "lat",
    "long",
}

# One row per (Site Down incident, Site) pair not yet Closed whose alarm
# hasn't cleared — behind the "Incident Site Down" card on the Custom
# Dashboard (reports/index.html), and read directly by the Telegram Site
# Down alert (app/services/telegram/telegram_alert.py) instead of that
# alert querying Postgres a second time for the same data. Same join/filter
# as app/database/queries/incident_site_down.sql, minus Incident Status filtering
# since this card shows every matching status. A multi-site incident is
# more than one row here, one per site, sharing the same incident_id. See
# app/services/incident/incident_sync_service.py for the sync.
INCIDENT_SITE_DOWN_CACHE_TABLES = ("incident_site_down",)

_INCIDENT_SITE_DOWN_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        incident_id TEXT, incident_numeric_id INTEGER, incident_status TEXT, wo_id TEXT,
        wo_numeric_id INTEGER, wo_created_at TEXT, wo_status TEXT, site_name TEXT, site_code TEXT,
        occurred_at TEXT, l1_noc_investigation_result TEXT, last_comments TEXT, nms TEXT,
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
    "nms",
    "hub_site",
    "site_grade",
    "province",
    "district",
    "commune",
}

# One row per Site Down incident found on the Telegram alert's last run
# (app/services/telegram/telegram_alert.py, every ALERT_INTERVAL_SECONDS) —
# same shape as incident_site_down, kept as its own table so the alert's
# own data (plus its computed outage_min) is inspectable independent of
# the dashboard card's cache. Not filtered by ALERT_THRESHOLD_MIN — that
# filtering happens in Python after this cache is written, so this table
# always reflects every current Site Down incident, not just the ones that
# were over-threshold and actually sent.
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

# Same "every row seen on the alert's last run, not just the ones over
# threshold" role as telegram_alert_cache above, but for the INC-WO Site
# Down Telegram alert (app/services/telegram/telegram_inc_wo_alert.py) —
# kept as its own table since replace_all() wipes the whole table on every
# run, and this alert reads a different source (inc_wo_site_down) with a
# different row shape (wo_created_at instead of occurred_at as the "age"
# field, fault_description instead of l1_noc_investigation_result/
# last_comments) — sharing telegram_alert_cache would silently overwrite
# the other alert's last-run snapshot with this one's.
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

# Same "every row seen on the alert's last run" role as
# telegram_inc_wo_alert_cache above, but for the Category Power alert —
# kept as its own table so replace_all() can't overwrite another alert's
# last-run snapshot.
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

# Same "every row seen on the alert's last run" role as
# telegram_inc_wo_power_alert_cache above, but for the General alert —
# kept as its own table so replace_all() can't overwrite another alert's
# last-run snapshot.
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

# One row per active NE/connectivity alarm (object_138) — the broader
# VVIP/Mentor/RAN alarm set (NodeB/eNodeB out of service, CSL Fault, NE
# Disconnected, Main Failure, Low DC Voltage, DG on, etc.), not just Main
# Failure. Site Code is resolved locally in Python (app/utils/get_processed_site.py,
# a port of Postgres's get_processed_site()) instead of by Postgres itself
# — see app/database/queries/ape_alarm.sql; Site Name is then resolved
# locally too, against the already-synced site_cache table — see
# app/services/ape_alarm/ape_alarm_sync_service.py.
APE_ALARM_CACHE_TABLES = ("ape_alarm",)

_APE_ALARM_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        occurred_at TEXT, event_name TEXT, additional_info TEXT,
        nms TEXT, technology TEXT, site_code TEXT, site_name TEXT, occurrence_count INTEGER
    )
"""

_APE_ALARM_CACHE_COLUMNS = {
    "occurred_at",
    "event_name",
    "additional_info",
    "nms",
    "technology",
    "site_code",
    "site_name",
    "occurrence_count",
}

# One row per active alarm (any event_name — no type filter) at a VIP/VVIP
# site — derived entirely locally by filtering the already-synced
# ape_alarm cache down to VIP/VVIP sites (site_strategic_type from
# site_cache), not by querying Postgres a second time. See
# app/services/vip/vip_alarm_sync_service.py.
VIP_ALARM_CACHE_TABLES = ("vip_alarm",)

_VIP_ALARM_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        occurred_at TEXT, event_name TEXT, additional_info TEXT,
        nms TEXT, technology TEXT, site_code TEXT, site_name TEXT, site_strategic_type TEXT,
        occurrence_count INTEGER
    )
"""

_VIP_ALARM_CACHE_COLUMNS = {
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

# Mirrors PostgreSQL's site_lookup_mv (sran_id/nodeb_id/bts_id -> site_name)
# — the same lookup table Postgres's own get_processed_site() PL/pgSQL
# function used to query internally, once per row of object_138. See
# app/utils/get_processed_site.py (the Python port of that function) and
# app/services/site/site_lookup_sync_service.py.
SITE_LOOKUP_CACHE_TABLES = ("site_lookup_cache",)

_SITE_LOOKUP_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        sran_id INTEGER, nodeb_id INTEGER, bts_id INTEGER, site_name TEXT
    )
"""

_SITE_LOOKUP_CACHE_COLUMNS = {"sran_id", "nodeb_id", "bts_id", "site_name"}

# One row per (site, technology) pair a site actually has an NE for
# (object_227, distinct — not the "first NE only" single_ne/sne CTE
# incident_site_down.sql/incident_by_status.sql use for the NMS code). technology is
# confirmed to only ever be '2g'/'3g'/'4g'/'5g'. Used by
# app/services/alarm_site_down/alarm_completely_site_down_service.py to know
# a site's full technology footprint, so it can tell whether every
# technology a site has is currently down (not just one). See
# app/database/queries/site_technology_cache.sql and
# app/services/site/site_sync_service.py.
SITE_TECHNOLOGY_CACHE_TABLES = ("site_technology_cache",)

_SITE_TECHNOLOGY_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        site_code TEXT, technology TEXT,
        PRIMARY KEY (site_code, technology)
    )
"""

_SITE_TECHNOLOGY_CACHE_COLUMNS = {"site_code", "technology"}

# One row per site with an NE (object_227) — the site's NMS vendor code,
# resolved ONCE here instead of being recomputed independently inside 6
# other queries via their own `single_ne`/`sne` window function over the
# whole object_227 table. See app/database/queries/ne_nms_lookup.sql and
# app/services/site/site_sync_service.py's sync_ne_nms().
NE_NMS_LOOKUP_CACHE_TABLES = ("ne_nms_lookup_cache",)

_NE_NMS_LOOKUP_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS {table} (
        site_code TEXT PRIMARY KEY, nms_code TEXT
    )
"""

_NE_NMS_LOOKUP_CACHE_COLUMNS = {"site_code", "nms_code"}

# (cache table names, CREATE TABLE template, expected columns) — used by
# init_cache_db() below to create each group and drop-and-recreate any table
# whose columns are stale (these are pure caches, so that's always safe).
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
        INCIDENT_SITE_DOWN_CACHE_TABLES,
        _INCIDENT_SITE_DOWN_TABLE_SCHEMA,
        _INCIDENT_SITE_DOWN_CACHE_COLUMNS,
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
)

# Tables no longer synced by anything — dropped on startup so an existing
# instance/localstorage.db doesn't keep stale, unread data around forever.
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
    """`timeout=10` already sets SQLite's busy-timeout (10s) — matches
    PRAGMA busy_timeout=10000, just via the sqlite3 module's own connect()
    argument rather than a separate PRAGMA. WAL mode is the piece that
    wasn't set anywhere: SQLite's default rollback-journal mode holds an
    exclusive lock for a writer's whole transaction, blocking every other
    reader AND writer — with this many background sync threads (site,
    incident, ape_alarm, vip_*, all_tasks_summary, dashboard heartbeat,
    ...) all touching the same instance/localstorage.db concurrently, that
    produced real "database is locked" errors under load. WAL lets readers
    proceed while a writer is active (only writer-vs-writer still
    serializes), which is a much better fit for this access pattern. It's
    a setting stored in the database file itself, not the connection, so
    this PRAGMA is a fast no-op on every connection after the first one
    that actually switches it over."""
    conn = sqlite3.connect(db_path(), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


def _expected_pk_columns(schema):
    """Primary key column name(s) a CREATE TABLE schema string declares —
    either a trailing `PRIMARY KEY (col1, col2)` clause, or an inline
    `col TYPE PRIMARY KEY`. Used by init_cache_db() to also catch a
    PRIMARY KEY change (e.g. incident_id -> (incident_id, site_code)) as a
    schema mismatch, since the plain column-name comparison alone can't see
    that — same set of column names, different key."""
    composite = re.search(r"PRIMARY KEY\s*\(([^)]+)\)", schema, re.IGNORECASE)
    if composite:
        return {c.strip() for c in composite.group(1).split(",")}
    inline = re.search(r"(\w+)\s+\w+\s+PRIMARY KEY", schema, re.IGNORECASE)
    return {inline.group(1)} if inline else set()


def init_cache_db() -> None:
    """Create the cache tables if they don't exist yet. Safe to call on every
    app startup — idempotent, and cheap enough not to worry about. These are
    pure caches (the next sync cycle repopulates them within seconds), so a
    schema change just drops and recreates the table rather than migrating it."""
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
        conn.execute(
            "CREATE TABLE IF NOT EXISTS sync_meta ("
            "table_name TEXT PRIMARY KEY, last_synced_at TEXT)"
        )
        # mentor_sites holds site codes the user has explicitly typed in or
        # uploaded via the Mentor Site page (app/routes/mentor.py) — NOT a
        # Postgres/MSSQL sync cache like every table above. Deliberately
        # created with plain CREATE TABLE IF NOT EXISTS, outside the
        # _CACHE_DEFINITIONS drop-and-recreate loop: those tables are safe
        # to drop on a schema mismatch because the next sync cycle
        # repopulates them, but this table holds data only the user can
        # recreate — it must never be dropped automatically.
        conn.execute(
            "CREATE TABLE IF NOT EXISTS mentor_sites ("
            "site_code TEXT PRIMARY KEY, added_at TEXT, source TEXT)"
        )
        conn.commit()
    finally:
        conn.close()
