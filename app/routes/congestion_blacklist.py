"""Local, reversible congestion exclusions; never writes to MSSQL."""
import getpass
from urllib.parse import urlsplit

from flask import Blueprint, abort, redirect, render_template, request, url_for

from app.repositories.alarm.alarm_cache_repository import AlarmCacheRepository
from app.repositories.alarm.congestion_blacklist_repository import CongestionBlacklistRepository
from app.services.alarm.congestion_blacklist_service import CongestionBlacklistService

congestion_blacklist_bp = Blueprint("congestion_blacklist", __name__)
_TABLES = {"eze": "eze_alarm_cache", "tct": "tct_alarm_cache", "congestion_history": "congestion_history_cache"}


def _return_to():
    target = request.form.get("return_to", "")
    parsed = urlsplit(target)
    if not parsed.scheme and not parsed.netloc and parsed.path in {"/", "/drilldown", "/congestion"}:
        return target
    return url_for("dashboard.congestion")


@congestion_blacklist_bp.get("/alarms/congestion/blacklist")
def index():
    return render_template("drilldown/_congestion_blacklist_rows.html", rules=CongestionBlacklistRepository().fetch_all())


@congestion_blacklist_bp.post("/alarms/congestion/exclude")
def exclude():
    source = request.form.get("source", "")
    row_id = request.form.get("id", "").strip()
    if source not in _TABLES or not row_id:
        abort(400, "Select a valid Ezecom or Telcotech congestion record.")
    rows = AlarmCacheRepository().fetch_where(_TABLES[source], "id = ?", (row_id,))
    if not rows:
        abort(404, "The alarm is no longer in the cache. Refresh and try again.")
    try:
        CongestionBlacklistService().exclude(rows[0], source, getpass.getuser(), request.form.get("remark", ""))
    except ValueError as exc:
        abort(400, str(exc))
    return redirect(_return_to())


@congestion_blacklist_bp.post("/alarms/congestion/blacklist/<int:rule_id>/restore")
def restore(rule_id):
    CongestionBlacklistRepository().remove(rule_id)
    return redirect(_return_to())
