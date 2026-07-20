"""Business logic for the ISP POP / EZE / TCT / IT NODE alarm cards.

Reads from the local cache (instance/localstorage.db, see app/database/cache.py)
that app/services/alarm_scheduler.py keeps in sync with MSSQL in the background — pages
never wait on a live MSSQL query. Each card always reports its full fixed set
of alarm types: a type with no active alarms comes back as 0 (rendered green)
instead of disappearing, so the card layout never shifts.
"""
from app.repositories.alarm_cache_repository import AlarmCacheRepository
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
    def __init__(self, cache_repository=None):
        self.cache_repository = cache_repository or AlarmCacheRepository()

    # ── Badge counts (used by the dashboard cards) ──────────────────
    # Each of these returns a dict of {alarm type: count}, used to fill in
    # the number badges on a card. See get_*_details() below for the full
    # row data behind a drilldown table.

    def get_isp_pop_counts(self):
        """{'POP/PON DOWN': n, 'POP/PON POWER': n} for the ISP POP badges."""
        rows = self.cache_repository.fetch_all("isp_pop_alarm_cache")
        counts = {"POP/PON DOWN": 0, "POP/PON POWER": 0}
        for r in rows:
            alarm = r.get("alarm")
            if alarm in counts:
                counts[alarm] += 1
        return counts

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
        """Count rows per alarm type, matched case-insensitively (EZE
        stores its type in UPPERCASE, TCT in lowercase).

        `always_types` is returned in full even for a type with 0 matching
        rows — that's what makes a badge show a green "0" instead of
        disappearing when there's nothing wrong.
        """
        by_upper = {}
        for r in rows:
            t = (r.get("alarm") or "").strip()
            if not t:
                continue
            by_upper[t.upper()] = by_upper.get(t.upper(), 0) + 1
        return {t: by_upper.get(t.upper(), 0) for t in always_types}
