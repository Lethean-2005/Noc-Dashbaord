"""
webhook/main_failure.py — RAN/Alarm Main Failure alarms -> Teams.
Run:  python webhook/main_failure.py          (or --dry-run to preview)
URL:  TEAMS_WEBHOOK_MAIN_FAILURE in .env
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from webhook.common import AlertSpec, run_cli


def _fetch():
    from app.services.alarm_main_failure.alarm_main_failure_service import AlarmMainFailureService
    return AlarmMainFailureService().get_details()


COLUMNS = [
    ("#", "_idx"),
    ("Incident ID", "incident_id"),
    ("INC-WO ID", "wo_id"),
    ("INC-WO Created", "wo_created_at"),
    ("INC-WO Status", "wo_status"),
    ("Site Name", "site_name"),
    ("Site Code", "site_code"),
    ("NMS", "nms"),
    ("Event", "event_name"),
    ("Occurred At", "occurred_at"),
    ("Outage(min)", "outage_min"),
    ("Grade", "site_grade"),
    ("Province", "province"),
]

SPEC = AlertSpec(
    key="main_failure",
    title="Alarm Main Failure",
    env_var="TEAMS_WEBHOOK_MAIN_FAILURE",
    fetch=_fetch,
    columns=COLUMNS,
    report_path="/drilldown?scope=Alarm%20Main%20Failure&title=Alarm%20Main%20Failure",
)


if __name__ == "__main__":
    sys.exit(run_cli(SPEC))
