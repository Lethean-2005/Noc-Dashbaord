"""
webhook/inc_wo_site.py — INC-WO Site Down work orders -> Teams.
Run:  python webhook/inc_wo_site.py           (or --dry-run to preview)
URL:  TEAMS_WEBHOOK_INC_WO_SITE_DOWN in .env
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from webhook.common import AlertSpec, run_cli


def _fetch():
    from app.services.incwo.incwo_service import IncWoService
    return IncWoService().get_site_down_details()


COLUMNS = [
    ("#", "_idx"),
    ("Incident ID", "incident_id"),
    ("INC-WO ID", "wo_id"),
    ("INC-WO Created At", "wo_created_at"),
    ("INC-WO Status", "wo_status"),
    ("Site Name", "site_name"),
    ("Site Code", "site_code"),
    ("Overdue", "overdue"),
    ("Support Level", "support_level"),
    ("Fault Description", "fault_description"),
    ("NMS", "nms"),
    ("Hub Site", "hub_site"),
    ("Site Grade", "site_grade"),
    ("Province", "province"),
    ("District", "district"),
    ("Commune", "commune"),
]

SPEC = AlertSpec(
    key="inc_wo_site",
    title="INC-WO Site Down",
    env_var="TEAMS_WEBHOOK_INC_WO_SITE_DOWN",
    fetch=_fetch,
    columns=COLUMNS,
    report_path="/drilldown?scope=INC-WO%20Site%20Down&title=INC-WO%20Site%20Down",
)


if __name__ == "__main__":
    sys.exit(run_cli(SPEC))
