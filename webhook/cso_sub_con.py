"""
webhook/cso_sub_con.py — CSO Sub-Con -> Teams.
Same data as current_site_down.py (Alarm Site Down), posted to the
CSO-Sub-Con channel instead.
Run:  python webhook/cso_sub_con.py           (or --dry-run to preview)
URL:  TEAMS_WEBHOOK_CSO_SUB_CON in .env
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from webhook.common import AlertSpec, run_cli
from webhook.current_site_down import SPEC as _CURRENT_SITE_DOWN


SPEC = AlertSpec(
    key="cso_sub_con",
    title="CSO Sub-Con - Current Site Down",
    env_var="TEAMS_WEBHOOK_CSO_SUB_CON",
    fetch=_CURRENT_SITE_DOWN.fetch,
    columns=_CURRENT_SITE_DOWN.columns,
    report_path=_CURRENT_SITE_DOWN.report_path,
)


if __name__ == "__main__":
    sys.exit(run_cli(SPEC))
