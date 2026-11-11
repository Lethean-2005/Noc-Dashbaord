"""Shared Smart Report period and elapsed-time formatting."""
import calendar
from datetime import datetime
import re
from zoneinfo import ZoneInfo

_MONTHS = {name.lower(): index for index in range(1,13)
           for name in (calendar.month_name[index], calendar.month_abbr[index])}
_PERIOD = re.compile(r"^([A-Za-z]+)(?:\s*[-\u2013/]\s*([A-Za-z]+))?\s+(\d{4})$")


def short_report_period(value):
    match = _PERIOD.fullmatch(str(value or "").strip())
    if not match:
        return ""
    first, last, year = match.groups()
    if first.lower() not in _MONTHS or last and last.lower() not in _MONTHS:
        return ""
    months = calendar.month_abbr[_MONTHS[first.lower()]]
    if last:
        months += "-" + calendar.month_abbr[_MONTHS[last.lower()]]
    return months + " " + year


def report_year_suffix(value):
    match = re.search(r"\b(\d{4})\b", str(value or ""))
    year = match.group(1) if match else str(datetime.now(ZoneInfo("Asia/Phnom_Penh")).year)
    return year[-2:]


def reaction_delay(complaint, response):
    """No invented midnight wrap or SLA/credit assumption for invalid times."""
    def parse(value):
        for pattern in ("%d-%b-%Y %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(str(value or "").strip(), pattern)
            except ValueError:
                pass
        return None
    start, end = parse(complaint), parse(response)
    if start is None or end is None or end < start:
        return ""
    minutes = int((end-start).total_seconds() // 60)
    return f"{minutes // 60:02d}hrs {minutes % 60:02d}mins"
