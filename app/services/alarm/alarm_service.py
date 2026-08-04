"""Business logic for the ISP POP / EZE / TCT / IT NODE alarm cards.

Reads from the local cache (instance/localstorage.db, see app/database/cache.py)
that app/services/alarm/alarm_scheduler.py keeps in sync with MSSQL in the background — pages
never wait on a live MSSQL query. Each card always reports its full fixed set
of alarm types: a type with no active alarms comes back as 0 (rendered green)
instead of disappearing, so the card layout never shifts.
"""
from app.repositories.alarm.alarm_cache_repository import AlarmCacheRepository
from app.repositories.alarm.alarm_repository import AlarmRepository
from app.utils.datetime import elapsed_minutes

EZE_TYPES = (
    "BANDWIDTH", "CPU", "CRC", "DOOR", "PORT",
    "RECTIFIER_BATTERY_TEMPERATURE", "TEMPERATURE",
)
TCT_TYPES = (
    "bandwidth", "bgp", "congestion", "cpu", "crc", "dldp",
    "memory", "node", "port", "storm", "switch_signal_low",
    "tx_ofa_port", "tx_otu/eth", "tx_temperature", "zero_traffic",
)


class AlarmService:
    def __init__(self, cache_repository=None, mssql_repository=None):
        self.cache_repository = cache_repository or AlarmCacheRepository()
        self.mssql_repository = mssql_repository or AlarmRepository()

    # ── Badge counts (used by the dashboard cards) ──────────────────
    # Each of these returns a dict of {alarm type: count}, used to fill in
    # the number badges on a card. See get_*_details() below for the full
    # row data behind a drilldown table.

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

    def get_eze_counts(self):
        """One count per EZE_TYPES entry for the EZE badges."""
        rows = self.cache_repository.fetch_all("eze_alarm_cache")
        return self._typed_counts(rows, EZE_TYPES)

    def get_tct_counts(self):
        """One count per TCT_TYPES entry for the TCT badges."""
        rows = self.cache_repository.fetch_all("tct_alarm_cache")
        return self._typed_counts(rows, TCT_TYPES)

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

    # ── Acknowledge / Modify (EZE / TCT / ISP POP drilldowns) ────────

    def acknowledge_note(self, row_id, tt_inc_wo_id, note, username):
        """Writes back to the real MSSQL row (not the local cache — the
        next MSSQL_SYNC_INTERVAL_SECONDS sync cycle picks the change up
        from there, same as every other MSSQL-sourced field). `note` is
        combined with `tt_inc_wo_id` into the single NOTE column MSSQL
        actually has; ACK/AB vs MD/MB are decided by
        AlarmRepository.acknowledge_note() based on whether this row has
        ever been acknowledged before. `row_id` is TBL_PPD.ID (a
        uniqueidentifier), not RTID — RTID was confirmed live to repeat
        across unrelated rows, so it can't safely identify a single row.
        Returns True if a row was actually updated (False means this id no
        longer matches any open alarm — e.g. it cleared between page load
        and submit)."""
        combined_note = f"{tt_inc_wo_id}: {note}" if tt_inc_wo_id else note
        rows_affected = self.mssql_repository.acknowledge_note(row_id, combined_note, username)
        return rows_affected > 0

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
    def _typed_counts(rows, always_types):
        """Count distinct devices per alarm type, matched case-insensitively
        (EZE stores its type in UPPERCASE, TCT in lowercase) — not the raw
        row count, since a single device can carry more than one row for
        the same alarm type.

        `always_types` is returned in full even for a type with 0 matching
        rows — that's what makes a badge show a green "0" instead of
        disappearing when there's nothing wrong.
        """
        devices_by_upper = {}
        for r in rows:
            t = (r.get("alarm") or "").strip()
            device_name = r.get("device_name")
            if not t or not device_name:
                continue
            devices_by_upper.setdefault(t.upper(), set()).add(device_name)
        return {t: len(devices_by_upper.get(t.upper(), set())) for t in always_types}
