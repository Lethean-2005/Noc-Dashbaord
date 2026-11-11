"""Persistent exclusions for one owner, device and congestion interface."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from app.repositories.alarm.congestion_blacklist_repository import CongestionBlacklistRepository


def is_congestion(row):
    alarm = str(row.get("alarm_name") or row.get("alarm") or "").strip().lower()
    if alarm.startswith(("eze_", "tct_")):
        alarm = alarm[4:]
    return alarm in {"bandwidth", "congestion"}


def provider(row, source=None):
    if source in {"eze", "tct"}:
        return source
    name = str(row.get("alarm_name") or "").strip().lower()
    if name.startswith("eze_"):
        return "eze"
    if name.startswith("tct_"):
        return "tct"
    owner = str(row.get("pro_owner") or "").strip().lower()
    return {"ezecom": "eze", "telcotech": "tct"}.get(owner)


def match_key(row, source=None):
    owner = provider(row, source)
    interface = str(row.get("interface") or "").strip().casefold()
    if not owner or interface in {"", "-", "—"}:
        return None
    address = str(row.get("ip_address") or "").strip().casefold()
    name = str(row.get("device_name") or "").strip().casefold()
    if address and address not in {"-", "—"}:
        identity = ("ip", address, interface)
    elif name and name not in {"-", "—"}:
        identity = ("device", name, interface)
    else:
        return None
    return (owner, "interface", json.dumps(identity, separators=(",", ":")))



class CongestionBlacklistService:
    def __init__(self, repository=None):
        self.repository = repository or CongestionBlacklistRepository()

    def filter_rows(self, rows, source=None):
        # Reinterpret older saved entries narrowly; missing ports never hide a device.
        rules = {key for rule in self.repository.fetch_all()
                 if (key := match_key(rule, rule["source"])) is not None}
        if not rules:
            return rows
        return [row for row in rows if not (
            is_congestion(row) and match_key(row, source) in rules
        )]

    def exclude(self, row, source, username, remark=""):
        if not is_congestion(row):
            raise ValueError("Only congestion alarms can be excluded.")
        key = match_key(row, source)
        if key is None:
            raise ValueError("Select a congestion record with an owner, device and interface.")
        remark = str(remark or "").strip()
        if len(remark) > 1000:
            raise ValueError("Remark must be 1,000 characters or fewer.")
        owner, kind, value = key
        rule = {name: str(row.get(name) or "").strip() for name in
                ("pop_name", "pop_code", "device_name", "ip_address", "interface", "additional_info", "note")}
        rule.update(source=owner, match_kind=kind, match_value=value,
                    created_at=datetime.now(ZoneInfo("Asia/Phnom_Penh")).isoformat(timespec="seconds"),
                    created_by=username, remark=remark)
        self.repository.add(rule)
