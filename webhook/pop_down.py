"""
webhook/pop_down.py — POP/PON Down alarms -> Teams.
Run:  python webhook/pop_down.py             (or --dry-run to preview)
URL:  TEAMS_WEBHOOK_POP_DOWN in .env

Both this and pop_main_failure.py read the same isp_pop_alarm_cache (the ISP
POP card's data) and split it client-side by the `alarm` field's two values —
there is no separate cache table per alarm type, unlike EZE/TCT.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from webhook.common import AlertSpec, run_cli


def _fetch():
    from app.services.alarm.alarm_service import AlarmService
    rows = AlarmService().get_isp_pop_details()
    return [r for r in rows if r.get("alarm") == "POP/PON DOWN"]


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
    key="pop_down",
    title="POP/PON Down",
    env_var="TEAMS_WEBHOOK_POP_DOWN",
    fetch=_fetch,
    columns=COLUMNS,
    report_path="/drilldown?scope=ISP%20POP&type=POP%2FPON%20DOWN&title=POP%2FPON%20DOWN",
)


if __name__ == "__main__":
    sys.exit(run_cli(SPEC))
