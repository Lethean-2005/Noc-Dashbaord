"""
webhook/eze_alarm.py — EZE active alarms -> Teams.
Run:  python webhook/eze_alarm.py            (or --dry-run to preview)
URL:  TEAMS_WEBHOOK_EZE_ALERTS in .env  (falls back to TEAMS_WEBHOOK_URL)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from webhook.common import AlertSpec, run_cli, send


def _fetch():
    from app.services.alarm.alarm_service import AlarmService

    return AlarmService().get_eze_details()


COLUMNS = [
    ("#", "_idx"),
    ("TT/INC-WOID", "rtid"),
    ("POP Name", "pop_name"),
    ("POP Code", "pop_code"),
    ("Device", "device_name"),
    ("IP", "ip_address"),
    ("Alarm Name", "alarm_name"),
    ("Down Time", "down_time"),
    ("Outage(min)", "outage_min"),
    ("Interface", "interface"),
    ("Province", "province"),
    ("Note", "note"),
]

SPEC = AlertSpec(
    key="eze",
    title="EZE Active Alarms",
    env_var="TEAMS_WEBHOOK_EZE_ALERTS",
    env_fallback="TEAMS_WEBHOOK_URL",
    fetch=_fetch,
    columns=COLUMNS,
    report_path="/drilldown?scope=EZE&title=EZE%20Active%20Alarms",
)


def send_eze_teams_alert(max_rows: int = 40) -> dict:
    """Backward-compatible wrapper, matches the reference project's naming."""
    return send(SPEC, max_rows=max_rows)


if __name__ == "__main__":
    sys.exit(run_cli(SPEC))
