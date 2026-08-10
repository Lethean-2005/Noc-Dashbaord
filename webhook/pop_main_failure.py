"""
webhook/pop_main_failure.py — POP/PON Power (main failure) alarms -> Teams.
Run:  python webhook/pop_main_failure.py      (or --dry-run to preview)
URL:  TEAMS_WEBHOOK_POP_MAIN_FAILURE in .env

See pop_down.py — same isp_pop_alarm_cache, filtered to the other `alarm`
value.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from webhook.common import AlertSpec, run_cli


def _fetch():
    from app.services.alarm.alarm_service import AlarmService

    rows = AlarmService().get_isp_pop_details()
    return [r for r in rows if r.get("alarm") == "POP/PON POWER"]


COLUMNS = [
    ("#", "_idx"),
    ("POP Name", "pop_name"),
    ("POP Code", "pop_code"),
    ("Device", "device_name"),
    ("IP", "ip_address"),
    ("Alarm Name", "alarm_name"),
    ("Down Time", "down_time"),
    ("Outage(min)", "outage_min"),
    ("Root Cause", "root_cause"),
    ("Province", "province"),
    ("Note", "note"),
]

SPEC = AlertSpec(
    key="pop_main_failure",
    title="POP/PON Power Failure",
    env_var="TEAMS_WEBHOOK_POP_MAIN_FAILURE",
    fetch=_fetch,
    columns=COLUMNS,
    report_path="/drilldown?scope=ISP%20POP&type=POP%2FPON%20POWER&title=POP%2FPON%20POWER",
)


if __name__ == "__main__":
    sys.exit(run_cli(SPEC))
