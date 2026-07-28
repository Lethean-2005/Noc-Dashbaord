"""Mentor Sites page routes."""
from flask import Blueprint, Response, redirect, render_template, request, url_for

from app.services.mentor.mentor_site_service import MentorSiteService

mentor_bp = Blueprint("mentor", __name__)
mentor_site_service = MentorSiteService()


@mentor_bp.route("/")
def index():
    return render_template(
        "mentor/index.html",
        configured_sites=mentor_site_service.get_configured_sites(),
        added=request.args.get("added"),
        error=request.args.get("error"),
        invalid=request.args.get("invalid"),
        duplicate=request.args.get("duplicate"),
    )


@mentor_bp.route("/template")
def template():
    """CSV template for the "Import File" upload — just the site_code
    header, matching the column add_from_csv() looks for."""
    return Response(
        "site_code\n",
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=mentor_sites_template.csv"},
    )


@mentor_bp.route("/add", methods=["POST"])
def add():
    raw_text = request.form.get("site_codes", "")
    if not raw_text.strip():
        return redirect(url_for("mentor.index", error="No site code entered."))
    added, duplicate, invalid = mentor_site_service.add_site_codes(raw_text)
    if not added and not duplicate and not invalid:
        return redirect(url_for("mentor.index", error="No site code entered."))
    return redirect(url_for(
        "mentor.index",
        added=len(added) if added else None,
        duplicate=", ".join(duplicate) if duplicate else None,
        invalid=", ".join(invalid) if invalid else None,
    ))


@mentor_bp.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if not file or not file.filename:
        return redirect(url_for("mentor.index", error="No file selected."))
    added, duplicate, invalid, error = mentor_site_service.add_from_csv(file.stream)
    if error:
        return redirect(url_for("mentor.index", error=error))
    return redirect(url_for(
        "mentor.index",
        added=len(added) if added else None,
        duplicate=", ".join(duplicate) if duplicate else None,
        invalid=", ".join(invalid) if invalid else None,
    ))


@mentor_bp.route("/remove/<site_code>", methods=["POST"])
def remove(site_code):
    mentor_site_service.remove_site(site_code)
    return redirect(url_for("mentor.index"))


@mentor_bp.route("/clear", methods=["POST"])
def clear():
    mentor_site_service.clear_all_sites()
    return redirect(url_for("mentor.index"))
