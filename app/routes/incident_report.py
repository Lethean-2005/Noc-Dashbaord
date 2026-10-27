"""Incident Report page routes — one page styled like Telcotech's own
Wholesale Products & Service Delivery Incident Report template, with
editable fields laid directly on it (not a plain form/list flow). Saved
reports are switched between via a dropdown on that same page rather than
a separate list page; export as PDF/DOCX matches the same template (see
app/services/incident_report/incident_report_pdf.py's own header)."""

import io
import re

from flask import Blueprint, abort, redirect, render_template, request, send_file, url_for

from app.services.incident_report.incident_report_service import (
    IncidentReportService,
    annotate_chronology_events_with_headers,
)

incident_report_bp = Blueprint("incident_report", __name__)
incident_report_service = IncidentReportService()

_UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _export_filename(report, report_id, extension):
    """User-typed `file_name` (the "Export File Name" field on the
    document page) if set, sanitized for Windows/cross-platform safety
    and with any extension the user typed themselves stripped first (so
    "report.pdf" doesn't become "report.pdf.pdf") — otherwise the same
    IR_<Service Disruption> fallback this always used."""
    raw = (report.get("file_name") or "").strip()
    if not raw:
        raw = f"IR_{report.get('service_disruption') or report_id}"
    raw = re.sub(rf"\.{extension}$", "", raw, flags=re.IGNORECASE)
    safe = _UNSAFE_FILENAME_CHARS.sub("_", raw).strip(" .") or report_id
    return f"{safe}.{extension}"


@incident_report_bp.route("/")
def index():
    report_id = request.args.get("id")
    report = incident_report_service.get_report(report_id) if report_id else None
    report = dict(report) if report else {}
    # Groups chronology_events by their own date, same "Date and Time:
    # <date>" header-per-day grouping the DOCX/PDF export has always
    # used — see annotate_chronology_events_with_headers()'s own
    # docstring for why this needs to match the export exactly rather
    # than showing one static date pinned above the whole list.
    report["chronology_events"] = annotate_chronology_events_with_headers(
        report.get("chronology_events") or [], report.get("incident_date")
    )
    return render_template(
        "incident_report/document.html",
        report=report,
        report_id=report.get("id"),
        reports=incident_report_service.list_reports(),
    )


@incident_report_bp.route("/save", methods=["POST"])
def save():
    """"Save as Draft" (formnovalidate — skips the form's own `required`
    fields) vs "Save & Complete" (browser blocks the submit client-side
    unless every required field is filled) both post here; `intent`
    tells this route which button was clicked, purely to decide whether
    to also flip status to Final — the actual field-saving logic is
    identical either way."""
    report_id = request.form.get("report_id") or None
    intent = request.form.get("intent")
    # Picture Reference photos live in the DB as base64 (see
    # incident_report_service.py's own note on why), so a save that
    # doesn't touch them still needs the EXISTING report's own photos
    # passed through — parse_form() merges these with whichever
    # keep_picture_id values the form submitted plus any newly
    # uploaded files, rather than expecting the form to round-trip the
    # photos' own data.
    existing = incident_report_service.get_report(report_id) if report_id else None
    fields = incident_report_service.parse_form(
        request.form, request.files, existing.get("picture_references") if existing else None
    )
    if report_id and incident_report_service.update_report(report_id, fields):
        pass
    else:
        report_id = incident_report_service.create_report(fields)
    if intent == "final" and incident_report_service.is_complete(fields):
        incident_report_service.set_status(report_id, "Final")
    return redirect(url_for("incident_report.index", id=report_id))


@incident_report_bp.route("/<report_id>/delete", methods=["POST"])
def delete(report_id):
    incident_report_service.delete_report(report_id)
    return redirect(url_for("incident_report.index"))


@incident_report_bp.route("/<report_id>/status", methods=["POST"])
def set_status(report_id):
    """"Mark as Final"/"Revert to Draft" in the Actions menu. Marking
    Final goes through the SAME completeness check save()'s own
    intent == "final" path already enforces — this route used to skip
    it entirely, letting an incomplete report get marked Final here
    even though the footer's own "Save & Complete" button correctly
    refused to. Reverting to Draft has no such requirement (a Draft
    can always be incomplete)."""
    status = "Final" if request.form.get("status") == "Final" else "Draft"
    if status == "Final":
        report = incident_report_service.get_report(report_id)
        if report is None:
            abort(404)
        if not incident_report_service.is_complete(report):
            return redirect(url_for("incident_report.index", id=report_id, finalize_error=1))
    if not incident_report_service.set_status(report_id, status):
        abort(404)
    return redirect(url_for("incident_report.index", id=report_id))


@incident_report_bp.route("/<report_id>/pdf")
def export_pdf(report_id):
    report = incident_report_service.get_report(report_id)
    if report is None:
        abort(404)
    pdf_bytes = incident_report_service.render_pdf(report_id, report=report)
    if pdf_bytes is None:
        abort(404)
    filename = _export_filename(report, report_id, "pdf")
    return send_file(
        io.BytesIO(pdf_bytes), as_attachment=True, download_name=filename, mimetype="application/pdf"
    )


@incident_report_bp.route("/<report_id>/docx")
def export_docx(report_id):
    report = incident_report_service.get_report(report_id)
    if report is None:
        abort(404)
    docx_bytes = incident_report_service.render_docx(report_id, report=report)
    if docx_bytes is None:
        abort(404)
    filename = _export_filename(report, report_id, "docx")
    return send_file(
        io.BytesIO(docx_bytes),
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
