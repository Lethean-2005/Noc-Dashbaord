"""Pulls active alarms from MSSQL and writes them into the local cache
(instance/localstorage.db). This is the only place that talks to MSSQL for
the ISP POP / EZE / TCT / IT NODE cards — app/services/alarm/alarm_service.py
reads the cache that this writes, so request-time pages never wait on MSSQL.

Also owns sync_congestion_history() below — a DIFFERENT shape of sync
(a full historical refill, not active-only) for the Congestion History
dashboard card + drilldown, run on its own slower schedule by
congestion_history_scheduler.py rather than the 10s active-only
sync_all() cycle above.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import current_app

from app.repositories.alarm.alarm_cache_repository import AlarmCacheRepository
from app.repositories.alarm.alarm_repository import AlarmRepository
from app.repositories.alarm.congestion_flap_cache_repository import CongestionFlapCacheRepository
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Duplicated locally rather than cross-imported from
# incident_service.py's own private _now_local() — this codebase's
# established convention (every "now, Cambodia time" helper elsewhere
# is its own small private copy, not a shared util) over a premature
# shared abstraction for one line of code.
_LOCAL_TZ = ZoneInfo("Asia/Phnom_Penh")


def _now_local():
    return datetime.now(_LOCAL_TZ)

# One entry per card. Each is: (cache table to write into, the
# AlarmRepository method that fetches its MSSQL rows, which raw MSSQL
# column holds "the alarm type" for that card — ISP POP/IT NODE use
# AlarmName directly, EZE/TCT derive alarm_type from it in the SQL query
# itself).
_JOBS = (
    ("isp_pop_alarm_cache", "fetch_isp_pop_active", "AlarmName"),
    ("eze_alarm_cache", "fetch_eze_active", "alarm_type"),
    ("tct_alarm_cache", "fetch_tct_active", "alarm_type"),
    ("it_node_alarm_cache", "fetch_it_node_active", "AlarmName"),
)

# Same 4 jobs as _JOBS, keyed by the "source" value dashboard.py's
# _ALARM_SOURCE already resolves per scope — lets sync_scope() below
# refresh just the ONE table an Acknowledge/Clear action actually
# touched instead of sync_all()'s all 4.
_JOBS_BY_SOURCE = {
    "isp_pop": _JOBS[0],
    "eze": _JOBS[1],
    "tct": _JOBS[2],
    "it_node": _JOBS[3],
}

# How close together (restored_time of one row -> down_time of the
# next, same device) two Congestion rows have to be to count as the
# SAME flap episode rather than two separate ones — e.g. a device that
# clears and re-triggers 90 seconds later is still "one incident
# flapping", not two. No source-of-truth value for this exists anywhere
# (MSSQL never groups rows into episodes itself) — 5 minutes is this
# app's own chosen threshold, picked as a reasonable gap for "still the
# same event", not derived from real data.
_FLAP_GAP_MINUTES = 5


def _compute_flap_counts(rows, gap_minutes=_FLAP_GAP_MINUTES):
    """Groups `rows` (already-normalized congestion_history_cache rows)
    by (device_name, interface) — NOT device_name alone: a device with
    several interfaces each congesting independently would otherwise get
    unrelated interfaces' events merged into one shared episode just
    because they landed close together in time on the same device. Each
    group is sorted by down_time, then "flap episodes" are counted — a
    new episode starts whenever the gap since the previous row's
    restored_time exceeds `gap_minutes`; consecutive rows closer
    together than that are the same ongoing episode, not counted again.
    Returns {(device_name, interface): episode_count}. A row with an
    unparseable down_time is skipped entirely (can't be ordered); a row
    with no restored_time (still active) uses its own down_time as its
    "restored" point, same as _with_actual_duration()'s elapsed-to-now
    fallback reasoning — it can't end an episode before it started."""
    def _parse(value):
        try:
            return datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            return None

    by_key = {}
    for r in rows:
        device = r.get("device_name") or ""
        if not device:
            continue
        interface = r.get("interface") or ""
        by_key.setdefault((device, interface), []).append(r)

    counts = {}
    for key, key_rows in by_key.items():
        parsed = []
        for r in key_rows:
            down = _parse(r.get("down_time"))
            if down is None:
                continue
            restored = _parse(r.get("restored_time")) or down
            parsed.append((down, restored))
        parsed.sort(key=lambda pair: pair[0])

        episodes = 0
        episode_end = None
        for down, restored in parsed:
            if episode_end is None or (down - episode_end) > timedelta(minutes=gap_minutes):
                episodes += 1
                episode_end = restored
            elif restored > episode_end:
                episode_end = restored
        counts[key] = episodes
    return counts


class AlarmSyncService:
    def __init__(self, mssql_repository=None, cache_repository=None, flap_cache_repository=None):
        self.mssql_repository = mssql_repository or AlarmRepository()
        self.cache_repository = cache_repository or AlarmCacheRepository()
        self.flap_cache_repository = flap_cache_repository or CongestionFlapCacheRepository()

    def sync_all(self):
        """Refresh all 4 cache tables from MSSQL. Called every
        MSSQL_SYNC_INTERVAL_SECONDS by app/services/alarm/alarm_scheduler.py.
        Returns the total row count synced across all 4 tables (a table
        that failed contributes 0, same as an empty result — its own error
        is already logged by _sync_one() below) so the scheduler can report
        one combined "Total" line for the whole cycle."""
        total = 0
        for table, fetch_name, alarm_field in _JOBS:
            total += self._sync_one(table, fetch_name, alarm_field) or 0
        return total

    def sync_congestion_history(self, history_weeks=None):
        """Full historical refill of congestion_history_cache — every
        Congestion (bandwidth+congestion) alarm with DownTime in the
        last `history_weeks` ISO (Mon-start) weeks, active or long since
        cleared, replacing the table's full contents each cycle. Called
        on its own slower schedule (congestion_history_scheduler.py),
        separate from sync_all()'s 10s active-only loop above — this
        query reads a much wider, slower-changing window, so it doesn't
        need (and shouldn't pay the MSSQL cost of) that cadence. Returns
        the row count synced, or None on failure — same convention as
        _sync_one().

        `since` is the oldest labeled week's own Monday (mirrors
        AlarmService.get_congestion_weeks()'s identical Mon-start
        calculation), NOT "exactly history_weeks*7 days ago" — those two
        differ by up to 6 days (a rolling day-count cutoff almost never
        lands on a Monday), which left a real gap of rows: synced into
        the cache (so they counted in the dashboard card's own grand
        total) but older than every one of get_congestion_weeks()'s own
        week boundaries, so invisible to any per-week breakdown/filter
        (confirmed live — 529 real rows in that gap on 2026-10-02).
        Anchoring to the same Monday both sides already compute from
        guarantees every synced row falls inside one of the labeled
        weeks, so a per-week sum always equals the grand total."""
        weeks = history_weeks or current_app.config["CONGESTION_HISTORY_WEEKS"]
        today = _now_local().date()
        this_monday = today - timedelta(days=today.weekday())
        oldest_monday = this_monday - timedelta(weeks=weeks - 1)
        since = oldest_monday.strftime("%Y-%m-%d")
        try:
            rows = self.mssql_repository.fetch_congestion_history(since)
        except Exception as e:
            logger.error(f"MSSQL sync failed for congestion_history_cache (since={since}): {e}")
            return None
        # Logged even for a genuinely empty result — "0 rows, query ran
        # fine" (no Congestion alarms in this window) and "sync never
        # ran at all" (no log line at all) need to look different from
        # the server log alone, not just from this function's return
        # value, since there's no live MSSQL access from dev to verify
        # the query itself against real data.
        logger.info(f"MSSQL returned {len(rows)} row(s) for congestion_history (since={since})")

        normalized = [self._normalize(r, "alarm_type") for r in rows]
        try:
            self.cache_repository.replace_all("congestion_history_cache", normalized)
        except Exception as e:
            logger.error(f"Cache write failed for congestion_history_cache: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into congestion_history_cache")

        # Not read by any route/template yet (see congestion_flap_counts_cache's
        # own comment in app/database/cache.py) — recomputed here, right after
        # the data it's derived from changes, same as every other derived
        # cache in this file, rather than computed lazily on request.
        self._sync_congestion_flap_counts(normalized)
        return len(normalized)

    def _sync_congestion_flap_counts(self, normalized_rows):
        """Writes congestion_flap_counts_cache from the just-synced
        congestion_history_cache rows. Failure here is logged but never
        fails the main sync — this is a secondary, not-yet-surfaced
        derived number, not the Congestion History feature's own data."""
        now = _now_local().isoformat(timespec="seconds")
        counts = _compute_flap_counts(normalized_rows)
        flap_rows = [
            {"device_name": device, "interface": interface, "flap_count": count, "updated_at": now}
            for (device, interface), count in counts.items()
        ]
        try:
            self.flap_cache_repository.replace_all("congestion_flap_counts_cache", flap_rows)
        except Exception as e:
            logger.error(f"Cache write failed for congestion_flap_counts_cache: {e}")
            return
        logger.info(f"Synced {len(flap_rows)} device/interface pair(s) into congestion_flap_counts_cache")

    def sync_scope(self, source):
        """Refresh only the one cache table `source` (isp_pop/eze/tct/
        it_node) belongs to over a live MSSQL round trip — a full re-fetch
        of that whole table, not just one row. Acknowledge/Clear used to
        call this after every single click (see apply_acknowledge_result()/
        apply_clear() below for why that changed — this remains a correct,
        generic "resync just this one scope on demand" utility, just with
        no caller using it that way today). Unknown/missing source is a
        no-op (returns None), same tolerance as one failed table in
        sync_all()."""
        job = _JOBS_BY_SOURCE.get(source)
        if not job:
            return None
        table, fetch_name, alarm_field = job
        return self._sync_one(table, fetch_name, alarm_field)

    def apply_acknowledge_result(self, source, row_id, result):
        """Patches just the acknowledged row's note/ack/ab/mb/md directly
        into its cache table, using the exact values
        AlarmService.acknowledge_note()'s own trailing SELECT already
        returned — replaces a sync_scope() full-table re-fetch for this
        one action (confirmed live: every Acknowledge/Modify click was
        paying for a second live MSSQL round trip just to refresh the
        single row the write itself already touched). `result` is None
        when the row no longer exists at all (acknowledge_note()'s own
        rare case) — nothing to patch then; the next scheduled sync's own
        active-only WHERE clause will drop it from the cache if it's
        genuinely gone.

        Caught and logged, never raised — the real MSSQL write already
        committed by the time this runs (dashboard.py's acknowledge_alarm()
        calls this AFTER AlarmService.acknowledge_note() returns), so a
        local SQLite hiccup here must not turn an already-successful
        Acknowledge into a 500 for the user; same tolerance _sync_one()
        already has for the scheduled background sync path — a stale
        cached row here just means the next scheduled sync_all() catches
        it up within MSSQL_SYNC_INTERVAL_SECONDS, not silent data loss."""
        job = _JOBS_BY_SOURCE.get(source)
        if not job or result is None:
            return
        table, _, _ = job
        try:
            self.cache_repository.update_one(table, row_id, {
                "note": result.get("NOTE") or "",
                "ack": str(result.get("ACK") or ""),
                "ab": result.get("AB") or "",
                "md": str(result.get("MD") or ""),
                "mb": result.get("MB") or "",
            })
        except Exception as e:
            logger.error(f"Local cache patch failed for {table} row {row_id}: {e}")

    def apply_clear(self, source, row_id):
        """Removes the cleared row from its cache table directly —
        replaces sync_scope()'s full-table re-fetch for Clear Alarm, same
        reasoning as apply_acknowledge_result() above. Safe to call
        unconditionally, even when AlarmService.clear_alarm()'s own MSSQL
        write matched 0 rows (e.g. the device cleared it first) — either
        way, the row no longer belongs in an active-only cache table.
        Caught and logged, never raised — same reasoning as
        apply_acknowledge_result()'s own try/except above."""
        job = _JOBS_BY_SOURCE.get(source)
        if not job:
            return
        table, _, _ = job
        try:
            self.cache_repository.delete_one(table, row_id)
        except Exception as e:
            logger.error(f"Local cache delete failed for {table} row {row_id}: {e}")

    def _sync_one(self, table, fetch_name, alarm_field):
        """Fetch one card's rows from MSSQL and overwrite its cache table.
        Returns the row count synced, or None on failure.

        Both steps below are wrapped in their own try/except and `return`
        on failure instead of raising — this runs inside an infinite
        background loop (see alarm_scheduler.py), so any uncaught exception
        here would silently kill that loop forever. Logging and returning
        keeps this cycle a no-op (existing cache stays as-is, so a card
        shows slightly stale data rather than none) while leaving the loop
        itself free to try again next interval.
        """
        try:
            rows = getattr(self.mssql_repository, fetch_name)()
        except Exception as e:
            logger.error(f"MSSQL sync failed for {table}: {e}")
            return None

        normalized = [self._normalize(r, alarm_field) for r in rows]
        try:
            self.cache_repository.replace_all(table, normalized)
        except Exception as e:
            logger.error(f"Cache write failed for {table}: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {table}")
        return len(normalized)

    @staticmethod
    def _normalize(row, alarm_field):
        """Map MSSQL's column names (PascalCase, inconsistent across the 3
        queries) onto one consistent lowercase shape that the cache table,
        AlarmService, and the drilldown templates all agree on.

        `alarm` is the DERIVED type (e.g. 'port', 'congestion' for TCT — no
        prefix, lowercased) used internally for badge counting and the
        `type` drilldown filter; it must keep matching EZE_TYPES/TCT_TYPES.
        `alarm_name` is the RAW AlarmName column (e.g. 'TCT_PORT') used only
        for display in the drilldown table's Alarm Name column — never used
        for matching/filtering, so changing its format elsewhere is safe.

        `pro_owner` (Telcotech/Ezecom, colored in the drilldown table —
        see tables.css's .pop-owner-telcotech/.pop-owner-ezecom) is
        derived from AlarmName's own "TCT_"/"EZE_" prefix whenever one
        is present — both EZE and TCT are already single-owner by
        construction (every row an "EZE_..." or "TCT_..." alarm), so
        there's no need to depend on the isp_pop_alarm_cache query's
        own JOIN-sourced pro_owner column for those. ISP POP's own
        AlarmName ('POP/PON DOWN'/'POP/PON POWER') has neither prefix —
        falls through to row.get("pro_owner"), the ACTUAL per-row value
        isp_pop_alarm_cache's query joins from noc.TBL_POP.PRO_OWNER,
        since ISP POP genuinely mixes both owners' sites in one table.
        IT_NODE's own AlarmName ('IT_NODE') matches neither prefix
        either and has no pro_owner column to fall back to — stays
        blank there, which is correct (that drilldown shows no Owner
        column at all).
        """
        alarm_name = row.get("AlarmName") or ""
        if alarm_name.startswith("TCT_"):
            pro_owner = "Telcotech"
        elif alarm_name.startswith("EZE_"):
            pro_owner = "Ezecom"
        else:
            pro_owner = row.get("pro_owner") or ""
        return {
            "id": str(row.get("ID") or ""),
            "alarm": row.get(alarm_field) or row.get("AlarmName") or "",
            "alarm_name": alarm_name,
            "device_name": row.get("DeviceName") or "",
            "ip_address": row.get("IPAddress") or "",
            "pop_name": row.get("pop_name") or "",
            "pop_code": row.get("pop_code") or "",
            "province": row.get("Province") or "",
            "pro_owner": pro_owner,
            "down_time": str(row.get("DownTime") or ""),
            "restored_time": str(row.get("RestoredTime") or ""),
            "root_cause": row.get("PROBLEM_DETAILS") or row.get("PROBABLE_CAUSE") or "",
            "rtid": row.get("RTID") or "",
            "interface": row.get("INTERFACE") or "",
            "source_group": row.get("SourceGroup") or "",
            "additional_info": row.get("ADD_INFO") or "",
            "note": row.get("NOTE") or "",
            "ack": str(row.get("ACK") or ""),
            "ab": row.get("AB") or "",
            "mb": row.get("MB") or "",
            "md": str(row.get("MD") or ""),
        }
