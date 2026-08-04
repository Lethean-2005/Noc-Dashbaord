"""
webhook/dg_on.py — Alarm DG On alarms -> Teams.
Run:  python webhook/dg_on.py                 (or --dry-run to preview)
URL:  TEAMS_WEBHOOK_DG_ON in .env
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from webhook.common import AlertSpec, run_cli


def _fetch():
    from app.services.dg_on.dg_on_alarm_service import DgOnAlarmService
    return DgOnAlarmService().get_details()


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
    key="dg_on",
    title="Alarm DG On",
    env_var="TEAMS_WEBHOOK_DG_ON",
    fetch=_fetch,
    columns=COLUMNS,
    report_path="/drilldown?scope=Alarm%20DG%20On&title=Alarm%20DG%20On",
)


if __name__ == "__main__":
    sys.exit(run_cli(SPEC))
