"""Date/time helpers.

Named `datetime.py` to match the requested layout; import it as
`from app.utils import datetime as dt_utils` to avoid clashing with the stdlib module.
"""
from datetime import datetime


def elapsed_minutes(value):
    """Minutes since a 'YYYY-MM-DD HH:MM:SS'-like timestamp string. Returns 0
    if `value` is empty or doesn't parse — used for the drilldown Outage(min)
    column, computed at read time so it stays accurate between sync cycles."""
    if not value:
        return 0
    try:
        dt = datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S")
        return max(0, int((datetime.now() - dt).total_seconds() / 60))
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
