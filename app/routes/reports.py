"""Custom Dashboard page routes."""
from flask import Blueprint, render_template

from app.services.alarm.alarm_service import AlarmService
from app.services.alarm_site_down.alarm_completely_site_down_service import AlarmCompletelySiteDownService
from app.services.alarm_site_down.alarm_site_down_service import AlarmSiteDownService
from app.services.alarm_main_failure.alarm_main_failure_service import AlarmMainFailureService
from app.services.dg_on.dg_on_alarm_service import DgOnAlarmService
from app.services.incident.incident_service import IncidentService
from app.services.incwo.incwo_service import IncWoService

reports_bp = Blueprint("reports", __name__)
incwo_service = IncWoService()
alarm_service = AlarmService()
incident_service = IncidentService()
dg_on_alarm_service = DgOnAlarmService()
alarm_site_down_service = AlarmSiteDownService()
alarm_completely_site_down_service = AlarmCompletelySiteDownService()
alarm_main_failure_service = AlarmMainFailureService()


@reports_bp.route("/")
def index():
    return render_template(
        "reports/index.html",
        incident_site_down_counts=incident_service.get_incident_site_down_counts(),
        incwo_site_down_counts=incwo_service.get_site_down_counts(),
        incwo_resolved_count=incwo_service.get_resolved_count(),
        it_node_count=alarm_service.get_it_node_count(),
        dg_on_alarm_counts=dg_on_alarm_service.get_counts(),
        alarm_site_down_counts=alarm_site_down_service.get_counts(),
        alarm_completely_site_down_counts=alarm_completely_site_down_service.get_counts(),
        alarm_main_failure_counts=alarm_main_failure_service.get_counts(),
    )
