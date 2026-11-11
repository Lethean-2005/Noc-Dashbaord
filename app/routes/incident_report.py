"""Incident Report page routes — one page styled like Telcotech's own
Wholesale Products & Service Delivery Incident Report template, with
editable fields laid directly on it (not a plain form/list flow). Saved
reports are switched between via a dropdown on that same page rather than
a separate list page; export as PDF/DOCX matches the same template (see
app/services/incident_report/incident_report_pdf.py's own header)."""

import io
from app.utils.smart_report import short_report_period, report_year_suffix
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, current_app, redirect, render_template, request, send_file, url_for

from app.services.incident_report.incident_report_service import (
    IncidentReportService,
    annotate_chronology_events_with_headers,
)

incident_report_bp = Blueprint("incident_report", __name__)
incident_report_service = IncidentReportService()

_UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _current_report_month():
    """"November 2026" — Report Month's own default for a brand-new
    Smart Network Report, so a fresh report already names the month
    it's actually being filled in during, instead of starting blank.
    Editable afterward like every other field; this only seeds it."""
    return datetime.now(ZoneInfo(current_app.config["TIMEZONE"])).strftime("%B %Y")


def _smart_report_month_short(report_month):
    """Normalize single-month and month-range names without losing the year."""
    return short_report_period(report_month)


def _default_smart_file_name(report_month):
    short = _smart_report_month_short(report_month)
    return f"Smart Network Report_{short}" if short else "Smart Network Report"


def _export_filename(report, report_id, extension):
    """User-typed `file_name` (the "Export File Name" field on the
    document page) if set, sanitized for Windows/cross-platform safety
    and with any extension the user typed themselves stripped first (so
    "report.pdf" doesn't become "report.pdf.pdf") — otherwise the same
    IR_<Service Disruption> fallback this always used."""
    raw = (report.get("file_name") or "").strip()
    if not raw:
        if (report.get("report_type") or "incident") == "smart_network":
            raw = _default_smart_file_name(report.get("smart_report_month"))
        else:
            raw = f"IR_{report.get('service_disruption') or report_id}"
    raw = re.sub(rf"\.{extension}$", "", raw, flags=re.IGNORECASE)
    safe = _UNSAFE_FILENAME_CHARS.sub("_", raw).strip(" .") or report_id
    return f"{safe}.{extension}"


@incident_report_bp.route("/")
def index():
    report_id = request.args.get("id")
    report = incident_report_service.get_report(report_id) if report_id else None
    report = dict(report) if report else {}
    # An existing report's own saved report_type always wins (its type
    # never changes once created — see document.html's own type
    # dropdown docstring). Only a brand-new, unsaved report reads
    # ?type= — "+ New Report" under either dropdown option links here
    # with that param set, to decide which blank form to show.
    report_type = report.get("report_type") or request.args.get("type") or "incident"
    reports = incident_report_service.list_reports()
    if report_type == "smart_network":
        smart_reports = [r for r in reports if (r.get("report_type") or "incident") == "smart_network"]
        # Brand-new, unsaved report only (an existing one keeps whatever
        # it was actually saved with, blank or not):
        #   - Report Month defaults to the current month, and Export
        #     File Name follows from it, matching the "Smart Network
        #     Report_Sep 2027" style requested.
        #   - Document Title defaults to "Monthly Report" — the real
        #     template's own actual title (also what the export already
        #     falls back to when this is left blank), so the form shows
        #     the same title the PDF will, instead of looking blank
        #     while the export shows something anyway.
        #   - Customer Name carries over from the most recently updated
        #     Smart Network Report (smart_reports is already sorted
        #     newest-first — see IncidentReportRepository.fetch_all())
        #     — this report type is produced on a recurring monthly
        #     cadence for the SAME customer far more often than not, so
        #     retyping it every month is pure repetition; still blank
        #     when no prior report exists, same as before.
        if not report.get("id"):
            report.setdefault("smart_report_month", _current_report_month())
            report.setdefault(
                "file_name", _default_smart_file_name(report["smart_report_month"])
            )
            report.setdefault("document_title", "Monthly Report")
            if smart_reports:
                report.setdefault("smart_customer_name", smart_reports[0].get("smart_customer_name") or "")
        return render_template(
            "incident_report/smart_network_document.html",
            report=report,
            report_id=report.get("id"),
            report_type=report_type,
            reports=smart_reports,
            current_year_suffix=report_year_suffix(report.get("smart_report_month")),
        )
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
        report_type=report_type,
        reports=[r for r in reports if (r.get("report_type") or "incident") == "incident"],
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
    existing = incident_report_service.get_report(report_id) if report_id else None
    # An existing report's own type always wins (see index()'s own
    # note); a brand-new report reads report_type from its own hidden
    # form field, set by whichever blank template rendered it.
    report_type = (existing.get("report_type") if existing else None) or request.form.get(
        "report_type"
    ) or "incident"

    if report_type == "smart_network":
        fields = incident_report_service.parse_smart_form(request.form)
        is_complete_fn = incident_report_service.is_smart_complete
    else:
        # Picture Reference photos live in the DB as base64 (see
        # incident_report_service.py's own note on why), so a save that
        # doesn't touch them still needs the EXISTING report's own photos
        # passed through — parse_form() merges these with whichever
        # keep_picture_id values the form submitted plus any newly
        # uploaded files, rather than expecting the form to round-trip the
        # photos' own data.
        fields = incident_report_service.parse_form(
            request.form, request.files, existing.get("picture_references") if existing else None
        )
        is_complete_fn = incident_report_service.is_complete

    if report_id and incident_report_service.update_report(report_id, fields):
        pass
    else:
        report_id = incident_report_service.create_report(fields)
    if intent == "final" and is_complete_fn(fields):
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
        is_complete_fn = (
            incident_report_service.is_smart_complete
            if (report.get("report_type") or "incident") == "smart_network"
            else incident_report_service.is_complete
        )
        if not is_complete_fn(report):
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
