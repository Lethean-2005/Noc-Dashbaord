"""Business logic for the ISP POP / EZE / TCT / IT NODE alarm cards.

Reads from the local cache (instance/localstorage.db, see app/database/cache.py)
that app/services/alarm/alarm_scheduler.py keeps in sync with MSSQL in the background — pages
never wait on a live MSSQL query. Each card always reports its full fixed set
of alarm types: a type with no active alarms comes back as 0 (rendered green)
instead of disappearing, so the card layout never shifts.
"""

import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import current_app

from app.repositories.alarm.alarm_cache_repository import AlarmCacheRepository
from app.repositories.alarm.alarm_repository import AlarmRepository
from app.utils.datetime import elapsed_minutes
from app.utils.ttl_cache import ttl_cache

# Duplicated locally rather than cross-imported from incident_service.py's
# own private _now_local() — this codebase's established convention
# (every "now, Cambodia time" helper elsewhere is its own small private
# copy, not a shared util).
_LOCAL_TZ = ZoneInfo("Asia/Phnom_Penh")


def _now_local():
    return datetime.now(_LOCAL_TZ)


def _nice_ticks(max_value, intervals=5):
    """`intervals` evenly-spaced tick values from 0 up to a round number
    above `max_value` (1/2/5/10 x a power of ten). Duplicated locally
    rather than cross-imported from incident_service.py's own private
    copy — same light-duplication convention as this file's own
    _now_local() above."""
    if max_value <= 0:
        return [0] * (intervals + 1)
    raw_step = max_value / intervals
    magnitude = 10 ** math.floor(math.log10(raw_step))
    residual = raw_step / magnitude
    for candidate in (1, 2, 5, 10):
        if residual <= candidate:
            step = candidate * magnitude
            break
    else:
        step = 10 * magnitude
    return [round(step * i) for i in range(intervals + 1)]


EZE_TYPES = (
    "BANDWIDTH",
    "CPU",
    "CRC",
    "DOOR",
    "PORT",
    "RECTIFIER_BATTERY_TEMPERATURE",
    "TEMPERATURE",
)
TCT_TYPES = (
    "bandwidth",
    "bgp",
    "congestion",
    "cpu",
    "crc",
    "dldp",
    "memory",
    "node",
    "port",
    "storm",
    "switch_signal_low",
    "tx_ofa_port",
    "tx_otu/eth",
    "tx_temperature",
    "zero_traffic",
)

# The 2 TCT_TYPES entries merged into one "Congestion" count (see
# get_tct_counts() below). This exact pair is ALSO hardcoded as literal
# SQL text in alarms.sql's own congestion_history query (`IN ('bandwidth',
# 'congestion')`) — that file can't import this tuple, it's a separate
# language, so this constant can't make the SQL copy update itself if this
# one changes. test_alarm_service.py asserts this stays a subset of
# TCT_TYPES, so at least an accidental rename/drift breaks loudly in CI
# instead of silently undercounting Congestion History.
CONGESTION_TCT_TYPES = ("bandwidth", "congestion")


class AlarmService:
    def __init__(self, cache_repository=None, mssql_repository=None):
        self.cache_repository = cache_repository or AlarmCacheRepository()
        self.mssql_repository = mssql_repository or AlarmRepository()

    # ── Badge counts (used by the dashboard cards) ──────────────────
    # Each of these returns a dict of {alarm type: count}, used to fill in
    # the number badges on a card. See get_*_details() below for the full
    # row data behind a drilldown table.

    @ttl_cache(15)
    def get_isp_pop_counts(self):
        """{'POP/PON DOWN': n, 'POP/PON POWER': n} for the ISP POP badges —
        n is the number of distinct (POP Name, POP Code) sites with an
        active alarm of that type, not the raw row count (several devices
        at the same site can each carry their own row for the same alarm
        type). POP Name alone isn't a reliable site identity on its own
        (see AlarmRepository), so both fields together are the site key —
        scoped only to this one badge/card, not EZE/TCT's _typed_counts."""
        rows = self.cache_repository.fetch_all("isp_pop_alarm_cache")
        sites_by_type = {"POP/PON DOWN": set(), "POP/PON POWER": set()}
        for r in rows:
            pop_name = r.get("pop_name")
            pop_code = r.get("pop_code")
            alarm = r.get("alarm")
            if alarm in sites_by_type and pop_name:
                sites_by_type[alarm].add((pop_name, pop_code))
        return {alarm: len(sites) for alarm, sites in sites_by_type.items()}

    @ttl_cache(15)
    def get_eze_counts(self):
        """One count per EZE_TYPES entry for the EZE badges."""
        rows = self.cache_repository.fetch_all("eze_alarm_cache")
        return self._typed_counts(rows, EZE_TYPES)

    @ttl_cache(15)
    def get_tct_counts(self):
        """One count per TCT_TYPES entry for the TCT badges, except
        'bandwidth' and 'congestion' — two distinct alarm names MSSQL
        sends for the same underlying condition — which are merged into
        a single 'congestion' count so the card shows one Congestion
        badge instead of two. The drilldown for that badge matches both
        raw types too (see cards.html's data-type + _fetch_rows())."""
        rows = self.cache_repository.fetch_all("tct_alarm_cache")
        counts = self._typed_counts(rows, TCT_TYPES)
        # Written as literal keys, not unpacked from CONGESTION_TCT_TYPES by
        # position — "which of the two survives as the merged key" is a real
        # semantic (it must be 'congestion', the badge's own label) that a
        # tuple's position can silently invert if ever reordered. The
        # test below instead checks the SET of the two matches, which can't
        # flip direction.
        counts["congestion"] += counts.pop("bandwidth")
        return counts

    @ttl_cache(15)
    def get_it_node_count(self):
        """Single count of active IT_NODE alarms for the IT NODE card."""
        return len(self.cache_repository.fetch_all("it_node_alarm_cache"))

    # ── Full row detail (used by the drilldown table + CSV export) ──

    def get_isp_pop_details(self):
        """Every active ISP POP alarm row, with outage_min filled in."""
        return self._with_outage(self.cache_repository.fetch_all("isp_pop_alarm_cache"))

    def get_eze_details(self):
        """Every active EZE alarm row, with outage_min filled in."""
        return self._with_outage(self.cache_repository.fetch_all("eze_alarm_cache"))

    def get_tct_details(self):
        """Every active TCT alarm row, with outage_min filled in."""
        return self._with_outage(self.cache_repository.fetch_all("tct_alarm_cache"))

    def get_it_node_details(self):
        """Every active IT_NODE alarm row, with outage_min filled in."""
        return self._with_outage(self.cache_repository.fetch_all("it_node_alarm_cache"))

    def get_congestion_device_details(self, device_name):
        """Every Congestion alarm row for ONE device — what the Top
        Congestion Devices card's own drilldown actually shows. Uses
        fetch_where() (device_name pushed into the SQL WHERE, backed by
        idx_{table}_device_name — see app/database/cache.py) instead of
        get_congestion_history_details()'s fetch_all() + Python filter:
        the full congestion_history_cache table runs ~9-10k historical
        rows, and reading + dict-converting every one of them just to
        keep one device's few-hundred-to-few-thousand measured
        ~100-450ms per request before this, scaling with the WHOLE
        table's size regardless of how small the matched device is."""
        rows = self.cache_repository.fetch_where(
            "congestion_history_cache", "device_name = ?", (device_name,)
        )
        return self._with_actual_duration(rows)

    def get_congestion_device_interface_summary(self, device_name):
        """One row per Interface for `device_name` — what the device
        drilldown actually shows now, replacing the old one-row-per-
        alarm-event table for this scope: POP Name/Code/Owner/IP/
        Province are identical across every alarm on one device anyway,
        so only Interface (and Additional Info) ever actually varied row
        to row — Down Time/Restored Time/Alarm Name/Outage/Note/Action
        were the only columns that did, and those are intentionally not
        shown here anymore (still in the DB, just not surfaced in this
        view). Each interface's row uses its MOST RECENT alarm's own
        POP/Owner/IP/Province/Additional Info as a representative
        snapshot — get_congestion_device_details() rows are already
        down_time DESC (AlarmCacheRepository's own order_by), so the
        first row seen per interface is the newest. `total_count` is
        that interface's own raw alarm-row count (NOT the flap-episode
        count congestion_flap_counts_cache stores) — kept matching the
        Top Congestion Devices card's own count (also raw rows) after
        the two numbers disagreeing read as a bug rather than two
        different metrics once the user actually compared them live
        (215 raw rows vs. 48 flap episodes for one real device)."""
        rows = self.get_congestion_device_details(device_name)
        latest_by_interface = {}
        raw_counts = {}
        for r in rows:
            interface = r.get("interface") or ""
            if interface not in latest_by_interface:
                latest_by_interface[interface] = r
            raw_counts[interface] = raw_counts.get(interface, 0) + 1

        summary = [
            {
                "pop_name": r.get("pop_name") or "",
                "pop_code": r.get("pop_code") or "",
                "pro_owner": r.get("pro_owner") or "",
                "device_name": r.get("device_name") or "",
                "ip_address": r.get("ip_address") or "",
                "interface": interface,
                "province": r.get("province") or "",
                "additional_info": r.get("additional_info") or "",
                "total_count": raw_counts[interface],
            }
            for interface, r in latest_by_interface.items()
        ]
        summary.sort(key=lambda s: s["total_count"], reverse=True)
        return summary

    def get_congestion_week_details(self, congestion_week):
        """Every Congestion alarm row (ANY device) for ONE ISO Monday
        week — what clicking a week in the Top Congestion Devices card's
        own "Wk 37 · Wk 38 · ..." caption opens. Same fetch_where()
        reasoning as get_congestion_device_details() above: pushes the
        down_time range into SQL so only that week's rows (not all
        ~9-10k) get read + dict-converted. Invalid/unparseable
        `congestion_week` returns an empty list rather than raising —
        same tolerance as filter_congestion_week()'s own bad-input case."""
        try:
            monday = datetime.strptime(congestion_week, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return []
        start = monday.isoformat()
        end = (monday + timedelta(days=7)).isoformat()
        rows = self.cache_repository.fetch_where(
            "congestion_history_cache", "down_time >= ? AND down_time < ?", (start, end)
        )
        return self._with_actual_duration(rows)

    def get_congestion_week_interface_summary(self, congestion_week):
        """One row per (Device, Interface) for ONE ISO week, across
        EVERY device — what clicking a week in the Top Congestion
        Devices card's "Wk 37 · Wk 38 · ..." caption shows, mirroring
        get_congestion_device_interface_summary()'s own shape but scoped
        to a week instead of one device. `total_count` here is each
        (device, interface) pair's own raw alarm-row count within this
        week — kept matching the Top Congestion Devices card's own
        count (also raw rows), same reasoning as
        get_congestion_device_interface_summary()'s own docstring."""
        rows = self.get_congestion_week_details(congestion_week)
        latest_by_key = {}
        raw_counts = {}
        for r in rows:
            key = (r.get("device_name") or "", r.get("interface") or "")
            if key not in latest_by_key:
                latest_by_key[key] = r  # rows already down_time DESC
            raw_counts[key] = raw_counts.get(key, 0) + 1

        summary = [
            {
                "pop_name": r.get("pop_name") or "",
                "pop_code": r.get("pop_code") or "",
                "pro_owner": r.get("pro_owner") or "",
                "device_name": device,
                "ip_address": r.get("ip_address") or "",
                "interface": interface,
                "province": r.get("province") or "",
                "additional_info": r.get("additional_info") or "",
                "total_count": raw_counts[(device, interface)],
            }
            for (device, interface), r in latest_by_key.items()
        ]
        summary.sort(key=lambda s: s["total_count"], reverse=True)
        return summary

    # ── Top Congestion Devices (dashboard card) ───────────────────────

    def get_congestion_top_devices(self, limit=10, congestion_weeks=None):
        """Top `limit` devices by Congestion (bandwidth+congestion) alarm
        count over the full congestion_history_cache window (the last
        CONGESTION_HISTORY_WEEKS weeks — the cache itself is already
        scoped to that window, see AlarmSyncService.sync_congestion_history(),
        so no extra date filtering is needed here) — or the UNION of
        several ISO Monday weeks of it, if `congestion_weeks` narrows it
        (the card's own "Filter by Week" control — a checkbox list, so
        several weeks can be combined in one ranking; an empty list
        means "All", same as none selected). Same ranked-bars shape as
        IncidentService.get_top_site_down() (bar_width_pct scaled off
        _nice_ticks(), same as that card's own axis scaling even though
        this card doesn't render tick labels) — mirrored locally since
        this is alarm data, not incident data. `badge_type` is just the
        device name itself (no week-token suffix, unlike Top Site
        Down's "{site_code}_{week_token}") — clicking a bar's badge
        opens that device's own Interface summary
        (get_congestion_device_interface_summary()), independent of
        this card's own week filter. Any unrecognized value in
        `congestion_weeks` is silently dropped, same validate-in-the-
        service convention as IncidentService.get_top_site_down()'s own
        `week` param."""
        # Only device_name/down_time are read below — fetch_columns()
        # instead of fetch_all() skips building the other 17 columns'
        # worth of dict entries per row (measured: ~210ms of this card's
        # ~235ms on the real ~9-10k row table, see fetch_columns()'s own
        # docstring).
        rows = self.cache_repository.fetch_columns("congestion_history_cache", ["device_name", "down_time"])
        valid_isos = {w["iso"] for w in self.get_congestion_weeks()}
        selected_weeks = [w for w in (congestion_weeks or []) if w in valid_isos]
        if selected_weeks:
            rows = self.filter_congestion_weeks(rows, selected_weeks)
        counts = {}
        for r in rows:
            device = r.get("device_name") or ""
            if not device:
                continue
            counts[device] = counts.get(device, 0) + 1

        ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        max_count = ranked[0][1] if ranked else 0
        axis_max = _nice_ticks(max_count)[-1] or 1

        bars = [
            {
                "rank": i + 1,
                "device_name": device,
                "count": count,
                "bar_width_pct": round(count / axis_max * 100, 1),
                "badge_type": device,
            }
            for i, (device, count) in enumerate(ranked)
        ]

        return {
            "bars": bars,
            "total": sum(counts.values()),
            "weeks": self.get_congestion_weeks(),
            "selected_weeks": selected_weeks,
        }

    def get_congestion_weeks(self):
        """The Mon-Sun weeks pickable in the Congestion History device
        drilldown's own "Filter by Week" control — mirrors
        IncidentService's own _available_weeks() (ISO week, Mon-start,
        newest first, capped at this week) but driven by
        CONGESTION_HISTORY_WEEKS instead of that module's fixed
        _WEEKS_AVAILABLE, since this cache's own window is independently
        configurable. Duplicated rather than cross-imported for the same
        reason as _nice_ticks()/_format_tick() above."""
        weeks_available = current_app.config["CONGESTION_HISTORY_WEEKS"]
        today = _now_local().date()
        this_monday = today - timedelta(days=today.weekday())
        weeks = []
        for i in range(weeks_available):
            monday = this_monday - timedelta(days=7 * i)
            end = monday + timedelta(days=6)
            week_number = monday.isocalendar()[1]
            if i == 0:
                label = "This week"
            elif i == 1:
                label = "Last week"
            else:
                label = f"Week {week_number}"
            if monday.month == end.month:
                range_label = f"{monday.strftime('%b')} {monday.day}–{end.day}"
            else:
                range_label = f"{monday.strftime('%b')} {monday.day} – {end.strftime('%b')} {end.day}"
            weeks.append({
                "iso": monday.isoformat(),
                "label": label,
                "week_number": week_number,
                "range_label": range_label,
            })
        return weeks

    @staticmethod
    def filter_congestion_week(rows, congestion_week):
        """`rows` narrowed to one ISO Monday week (by down_time) for the
        Congestion History device drilldown's "Filter by Week" control.
        Empty/unrecognized `congestion_week` is a no-op (every row kept) —
        callers should validate against get_congestion_weeks() first if
        an invalid value must be treated as "All" rather than silently
        matching nothing."""
        if not congestion_week:
            return rows
        try:
            monday = datetime.strptime(congestion_week, "%Y-%m-%d").date()
        except ValueError:
            return rows
        date_strs = {(monday + timedelta(days=i)).isoformat() for i in range(7)}
        return [r for r in rows if (r.get("down_time") or "")[:10] in date_strs]

    @staticmethod
    def filter_congestion_weeks(rows, congestion_weeks):
        """`rows` narrowed to the UNION of several ISO Monday weeks — the
        Top Congestion Devices card's own multi-select "Filter by Week"
        checkboxes. Each week's own 7 dates are unioned into one set
        before filtering (not filter_congestion_week() called once per
        week and concatenated), so a row matching any selected week is
        kept exactly once. Empty list is a no-op (every row kept), same
        convention as filter_congestion_week()'s own empty-string case."""
        if not congestion_weeks:
            return rows
        date_strs = set()
        for congestion_week in congestion_weeks:
            try:
                monday = datetime.strptime(congestion_week, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                continue
            date_strs.update((monday + timedelta(days=i)).isoformat() for i in range(7))
        if not date_strs:
            return rows
        return [r for r in rows if (r.get("down_time") or "")[:10] in date_strs]

    # ── Acknowledge / Modify (EZE / TCT / ISP POP drilldowns) ────────

    def acknowledge_note(self, row_id, tt_inc_wo_id, note, username):
        """Writes back to the real MSSQL row. `note` is combined with
        `tt_inc_wo_id` into the single NOTE column MSSQL actually has;
        ACK/AB vs MD/MB are decided by AlarmRepository.acknowledge_note()
        based on whether this row has ever been acknowledged before.
        `row_id` is TBL_PPD.ID (a uniqueidentifier), not RTID — RTID was
        confirmed live to repeat across unrelated rows. Returns the row's
        final {NOTE, ACK, AB, MD, MB} dict straight from MSSQL's own
        trailing SELECT (same round trip as the write) — the caller
        (dashboard.py's acknowledge_alarm(), via
        AlarmSyncService.apply_acknowledge_result()) patches just this one
        row into the local cache directly with it, instead of the route
        re-fetching the whole table over MSSQL a second time just to
        refresh the single row this write already touched. None means
        row_id matched nothing at all (the row was deleted, not just
        cleared — genuinely rare)."""
        combined_note = f"{tt_inc_wo_id}: {note}" if tt_inc_wo_id else note
        return self.mssql_repository.acknowledge_note(row_id, combined_note, username)

    def clear_alarm(self, row_id, username):
        """Writes back to the real MSSQL row (not the local cache — same
        reasoning as acknowledge_note() above). Returns True if a row was
        actually cleared, False if it no longer matched a still-open alarm
        (e.g. it already cleared itself, or the id is stale)."""
        rows_affected = self.mssql_repository.clear_alarm(row_id, username)
        return rows_affected > 0

    # ── Shared helpers ───────────────────────────────────────────────

    @staticmethod
    def _with_outage(rows):
        """Add an 'outage_min' key to every row.

        Outage(min) is computed here, at read time, instead of being
        stored in the cache — that way it's always correct (minutes since
        down_time), even if the last MSSQL sync was several seconds ago.
        """
        for r in rows:
            r["outage_min"] = elapsed_minutes(r.get("down_time"))
        return rows

    @staticmethod
    def _with_actual_duration(rows):
        """Add an 'outage_min' key to every row, using the REAL
        down_time -> restored_time duration when restored_time is
        present (a cleared historical alarm), falling back to
        elapsed_minutes() (down_time -> now) only for a row that's
        still active — same fallback _with_outage() always uses, kept
        correct here instead of unconditionally measuring "to now" the
        way _with_outage() does, which would be wrong for any row
        that's already cleared."""
        for r in rows:
            restored = r.get("restored_time")
            outage_min = None
            if restored:
                try:
                    down = datetime.strptime(str(r.get("down_time"))[:19], "%Y-%m-%d %H:%M:%S")
                    rest = datetime.strptime(str(restored)[:19], "%Y-%m-%d %H:%M:%S")
                    outage_min = max(0, int((rest - down).total_seconds() / 60))
                except ValueError:
                    outage_min = None
            r["outage_min"] = outage_min if outage_min is not None else elapsed_minutes(r.get("down_time"))
        return rows

    @staticmethod
    def _typed_counts(rows, always_types):
        """Count alarms per type, matched case-insensitively (EZE stores
        its type in UPPERCASE, TCT in lowercase):

        - A row with a real POP link (pop_name AND pop_code both present —
          only true for rows that actually joined a POP device in MSSQL)
          is deduped by (pop_name, pop_code): several devices alarming at
          the same POP site count as 1 site, not N rows.
        - A row with no POP link (pop_name/pop_code empty — e.g. a core
          device with nothing to map to a POP) is counted as a plain
          record instead, one per row, since there's no site to dedupe
          by and each row is its own distinct occurrence.

        `always_types` is returned in full even for a type with 0 matching
        rows — that's what makes a badge show a green "0" instead of
        disappearing when there's nothing wrong.
        """
        sites_by_upper = {}
        raw_counts_by_upper = {}
        for r in rows:
            t = (r.get("alarm") or "").strip()
            if not t:
                continue
            pop_name = r.get("pop_name")
            pop_code = r.get("pop_code")
            key = t.upper()
            if pop_name and pop_code:
                sites_by_upper.setdefault(key, set()).add((pop_name, pop_code))
            else:
                raw_counts_by_upper[key] = raw_counts_by_upper.get(key, 0) + 1
        return {
            t: len(sites_by_upper.get(t.upper(), set())) + raw_counts_by_upper.get(t.upper(), 0)
            for t in always_types
        }
