"""Map View page routes."""

from flask import Blueprint, render_template

from app.services.map.map_view_service import MapViewService

map_view_bp = Blueprint("mapview", __name__)
map_view_service = MapViewService()


@map_view_bp.route("/")
def index():
    sites = map_view_service.get_sites()
    return render_template(
        "map/index.html", sites=sites, status_counts=map_view_service.get_status_counts(sites)
    )
