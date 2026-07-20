"""Custom Dashboard page routes."""
from flask import Blueprint, render_template

from app.services.alarm_service import AlarmService
from app.services.incident_service import IncidentService
from app.services.incwo_service import IncWoService

reports_bp = Blueprint("reports", __name__)
incwo_service = IncWoService()
alarm_service = AlarmService()
incident_service = IncidentService()


@reports_bp.route("/")
def index():
    return render_template(
        "reports/index.html",
        incident_site_down_counts=incident_service.get_incident_site_down_counts(),
        incwo_site_down_counts=incwo_service.get_site_down_counts(),
        incwo_resolved_count=incwo_service.get_resolved_count(),
        it_node_count=alarm_service.get_it_node_count(),
    )
