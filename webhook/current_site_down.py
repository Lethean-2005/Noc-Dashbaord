"""
webhook/current_site_down.py — Current Site Down Alarms (Alarm Site Down card,
at least one radio tech down) -> Teams.
Run:  python webhook/current_site_down.py     (or --dry-run to preview)
URL:  TEAMS_WEBHOOK_CURRENT_SITES_DOWN_ALARMS in .env
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from webhook.common import AlertSpec, run_cli


def _fetch():
    from app.services.alarm_site_down.alarm_site_down_service import AlarmSiteDownService

    return AlarmSiteDownService().get_details()


COLUMNS = [
    ("#", "_idx"),
    ("Incident ID", "incident_id"),
    ("INC-WO ID", "wo_id"),
    ("INC-WO Created", "wo_created_at"),
    ("INC-WO Status", "wo_status"),
    ("Site Name", "site_name"),
    ("Site Code", "site_code"),
    ("Event", "event_name"),
    ("Tech", "radio_technology"),
    ("Occurred At", "occurred_at"),
    ("Outage(min)", "outage_min"),
    ("NMS", "nms"),
    ("Hub Site", "hub_site"),
    ("Grade", "site_grade"),
    ("Province", "province"),
]

SPEC = AlertSpec(
    key="current_site_down",
    title="Current Site Down Alarms",
    env_var="TEAMS_WEBHOOK_CURRENT_SITES_DOWN_ALARMS",
    fetch=_fetch,
    columns=COLUMNS,
    report_path="/drilldown?scope=Alarm%20Site%20Down&title=Alarm%20Site%20Down",
)


if __name__ == "__main__":
    sys.exit(run_cli(SPEC))
