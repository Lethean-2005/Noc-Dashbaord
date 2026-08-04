"""
webhook/tct_alarm.py — TCT active alarms -> Teams.
Run:  python webhook/tct_alarm.py            (or --dry-run to preview)
URL:  TEAMS_WEBHOOK_TCT_DOWN in .env
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from webhook.common import AlertSpec, run_cli


def _fetch():
    from app.services.alarm.alarm_service import AlarmService
    return AlarmService().get_tct_details()


COLUMNS = [
    ("#", "_idx"),
    ("POP Name", "pop_name"),
    ("POP Code", "pop_code"),
    ("Device", "device_name"),
    ("IP", "ip_address"),
    ("Alarm Name", "alarm_name"),
    ("Down Time", "down_time"),
    ("Outage(min)", "outage_min"),
    ("Interface", "interface"),
    ("Province", "province"),
    ("Additional Info", "additional_info"),
    ("Note", "note"),
]

SPEC = AlertSpec(
    key="tct",
    title="TCT Active Alarms",
    env_var="TEAMS_WEBHOOK_TCT_DOWN",
    fetch=_fetch,
    columns=COLUMNS,
    report_path="/drilldown?scope=TCT%20Port%20Down%2FUp&title=TCT%20Active%20Alarms",
)


if __name__ == "__main__":
    sys.exit(run_cli(SPEC))
