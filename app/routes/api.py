"""JSON API endpoints consumed by the front-end JS."""
from flask import Blueprint, jsonify, request

from app.services.dashboard_service import DashboardService
from app.services.mentor_service import MentorService
from app.services.report_service import ReportService

api_bp = Blueprint("api", __name__)

dashboard_service = DashboardService()
report_service = ReportService()
mentor_service = MentorService()


@api_bp.route("/dashboard/summary")
def dashboard_summary():
    return jsonify(dashboard_service.get_summary())


@api_bp.route("/reports")
def reports():
    page = request.args.get("page", 1, type=int)
    return jsonify(report_service.list_reports(page=page))


@api_bp.route("/mentor/sessions")
def mentor_sessions():
    return jsonify(mentor_service.list_sessions())
