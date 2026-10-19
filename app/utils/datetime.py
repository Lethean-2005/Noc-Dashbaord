"""Date/time helpers.

Named `datetime.py` to match the requested layout; import it as
`from app.utils import datetime as dt_utils` to avoid clashing with the stdlib module.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

# Hardcoded rather than read from current_app.config["TIMEZONE"] — this
# function is called from plain service-layer code from dozens of call
# sites (RAN/VIP/alarm services etc.), including in unit tests that
# construct those services directly without a Flask app context, so
# depending on current_app here would require threading app_context()
# through all of them for no real benefit: this app has exactly one
# deployment, one NOC, one timezone, same as the hardcoded
# 'Asia/Phnom_Penh' in incident_sla_compliance_weekly.sql and its
# siblings (SQL can't read Flask config either).
_LOCAL_TZ = ZoneInfo("Asia/Phnom_Penh")


def elapsed_minutes(value):
    """Minutes since a 'YYYY-MM-DD HH:MM:SS'-like timestamp string. Returns 0
    if `value` is empty or doesn't parse — used for the drilldown Outage(min)
    column, computed at read time so it stays accurate between sync cycles.

    `value` is already Cambodia local time (postgres_sync_utils.py's
    to_local_seconds() converts it at sync time), so "now" needs to be
    explicitly Cambodia local too, not the server's raw system clock —
    same class of bug fixed in the SLA/Response/Resolution Time cards'
    week-bucketing (that one lived in Postgres, computed on raw UTC
    before Python ever saw the rows; this is the equivalent guard here)."""
    if not value:
        return 0
    try:
        dt = datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S")
        now = datetime.now(_LOCAL_TZ).replace(tzinfo=None)
        return max(0, int((now - dt).total_seconds() / 60))
    except ValueError:
        return 0


def format_short_date(date_str):
    """'2026-05-01' -> '1 May 2026'. Returns '' if empty/invalid.

    Built without strftime's day-of-month flag (%-d / %#d) since that flag
    isn't portable between Linux and Windows — this computes the same
    result by just formatting the day as a plain int.
    """
    if not date_str:
        return ""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return ""
    return f"{d.day} {d.strftime('%b %Y')}"
