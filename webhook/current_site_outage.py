"""
webhook/current_site_outage.py — Current Sites Outage -> Teams.
Same data as current_site_down.py (Alarm Site Down card / ape_alarm cache),
posted to the Current Sites Outage channel instead.
Run:  python webhook/current_site_outage.py   (or --dry-run to preview)
URL:  TEAMS_WEBHOOK_CURRENT_SITES_OUTAGE in .env
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from webhook.common import AlertSpec, run_cli
from webhook.current_site_down import SPEC as _CURRENT_SITE_DOWN


SPEC = AlertSpec(
    key="current_site_outage",
    title="Current Sites Outage",
    env_var="TEAMS_WEBHOOK_CURRENT_SITES_OUTAGE",
    fetch=_CURRENT_SITE_DOWN.fetch,
    columns=_CURRENT_SITE_DOWN.columns,
    report_path=_CURRENT_SITE_DOWN.report_path,
)


if __name__ == "__main__":
    sys.exit(run_cli(SPEC))
