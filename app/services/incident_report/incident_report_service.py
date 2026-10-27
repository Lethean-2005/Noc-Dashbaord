"""Business logic for the Incident Report page — CRUD over the local
incident_reports table plus PDF/DOCX export, matching Telcotech's own
Wholesale Products & Service Delivery Incident Report template (see
incident_report_pdf.py/incident_report_docx.py for where the layout came
from)."""

import base64
import json
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import current_app

from app.repositories.incident_report.incident_report_repository import (
    IncidentReportRepository,
)
from app.services.incident_report.incident_report_docx import build_docx
from app.services.incident_report.incident_report_pdf import build_pdf


def _event_sort_key(event):
    """Sorts chronology events chronologically (date, then time, both
    ascending) regardless of the order their rows were typed/arranged
    in on the form — confirmed needed live: a user with an event
    already at 1:27, then adding a second one at 1:26, expects the
    1:26 one to land ahead of it in time order, not wherever it was
    typed. Sorting once here (not in the JS or the docx/PDF builders)
    means every consumer of chronology_events_json — the on-page
    preview, the saved record, the exported document — sees the same
    already-correct order for free. Unparseable/blank date or time
    sorts last, not first, so an incomplete row doesn't jump ahead of
    real timestamped ones."""
    try:
        return (datetime.strptime(f"{event['date']} {event['time']}", "%d-%b-%Y %H:%M"),)
    except (ValueError, KeyError):
        return (datetime.max,)


def annotate_chronology_events_with_headers(events, incident_date):
    """Groups already-chronologically-sorted `events` (see
    _event_sort_key()) by their own `date`, for a "Date and Time:
    <date>" header to show once per group instead of repeating the
    date on every line — same grouping incident_report_docx.py's own
    export has always done (a chronology rolling past midnight gets
    its own new header right where the day changes), now shared here
    so the on-page web form shows the SAME grouping instead of a
    single static date pinned above the whole list regardless of how
    many different days the events actually span.

    Returns a NEW list of event dicts (shallow copies — originals
    untouched), each with an added "header_date" key: the date string
    to show as a header immediately before that event, or None if it
    continues the same day as the event before it. The very first
    event always gets a header — starting from `incident_date`, same
    as the export, so a chronology whose first event's own date
    hasn't been typed yet (or matches the incident date) still shows
    one initial header rather than none at all."""
    current_day = incident_date
    annotated = []
    for i, event in enumerate(events):
        event = dict(event)
        event_date = (event.get("date") or "").strip()
        if i == 0 or (event_date and event_date != current_day):
            event["header_date"] = event_date or current_day
            if event_date:
                current_day = event_date
        else:
            event["header_date"] = None
        annotated.append(event)
    return annotated


_TEXT_FIELDS = (
    "document_title",
    "file_name",
    "incident_raised_by",
    "incident_received_by",
    "reported_date",
    "service_disruption",
    "incident_date",
    "report_time",
    "incident_number",
    "incident_category",
    "customers_impacted",
    "duration_of_interruption",
    "raise_time",
    "restored_time",
    "details_date_and_time",
    "time_of_complaint",
    "issue_reported",
    "actions_taken_summary",
    "cause_of_outage",
    "fault_gps_location",
    "resolution",
    "permanent_fixed",
)

# Every report field, including file_name — mirrors the `required`
# attributes on document.html's own inputs. Server-side backstop for
# "Save & Complete": the browser's own HTML5 validation already blocks
# that submission client-side unless every one of these is filled in,
# but a request bypassing the browser (curl, JS disabled) shouldn't be
# able to mark a report Final just by setting intent=final — see
# routes/incident_report.py's save().
_REQUIRED_FIELDS = _TEXT_FIELDS

# "Add Second Fault" — deliberately NOT part of _TEXT_FIELDS/_REQUIRED_FIELDS:
# most reports have exactly one Fault Analysis & Resolution, and these
# only matter (and are only required — see is_complete() below) once
# has_second_fault is actually set. Read/stripped the same way as
# _TEXT_FIELDS, just kept in their own tuple so an ordinary single-fault
# report is never blocked on them. issued_time (the 1ST fault's own,
# no "_2" suffix) belongs here too, not in _TEXT_FIELDS — it's hidden on
# the form (document.html) for the same reason: a single fault has no
# "issued" moment separate from the fault itself.
_SECOND_FAULT_TEXT_FIELDS = (
    "issued_time",
    "cause_of_outage_2",
    "fault_gps_location_2",
    "issued_time_2",
    "resolution_2",
    "permanent_fixed_2",
)


class IncidentReportService:
    def __init__(self, repository=None):
        self.repository = repository or IncidentReportRepository()

    def list_reports(self):
        return self.repository.fetch_all()

    def get_report(self, report_id):
        return self.repository.get(report_id)

    def parse_form(self, form, files=None, existing_pictures=None):
        """Flask `request.form` (+ `request.files` for Picture Reference
        uploads) -> the plain dict every other method here and both doc
        builders share. Chronology events come in as three parallel
        lists (event_date[]/event_time[]/event_description[]) — each
        event carries its own date (not just time) so a chronology that
        rolls past midnight still shows which day every line belongs to.
        A blank trailing row from the "Add Event" button leaves all
        three fields empty, so those are dropped rather than saved as an
        empty bullet.

        `existing_pictures` (the report's own already-saved
        picture_references, if this is an update) lets a save keep
        whichever existing photos the user didn't remove — see
        _build_picture_references() below for why this can't just be
        round-tripped through the form itself."""
        fields = {name: (form.get(name) or "").strip() for name in _TEXT_FIELDS}
        fields["has_second_fault"] = (form.get("has_second_fault") or "").strip()
        fields.update({name: (form.get(name) or "").strip() for name in _SECOND_FAULT_TEXT_FIELDS})

        dates = form.getlist("event_date")
        times = form.getlist("event_time")
        descriptions = form.getlist("event_description")
        events = sorted(
            (
                {"date": dt.strip(), "time": t.strip(), "description": d.strip()}
                for dt, t, d in zip(dates, times, descriptions)
                if dt.strip() or t.strip() or d.strip()
            ),
            key=_event_sort_key,
        )
        fields["chronology_events_json"] = json.dumps(events)

        items = [item.strip() for item in form.getlist("improvement_item") if item.strip()]
        fields["improvement_plan_json"] = json.dumps(items)

        pictures = self._build_picture_references(form, files, existing_pictures or [])
        fields["picture_references_json"] = json.dumps(pictures)
        return fields

    @staticmethod
    def _build_picture_references(form, files, existing_pictures):
        """Merges whichever existing Picture Reference photos the user
        kept (checked via keep_picture_id — a plain list of ids, not the
        photos themselves: a hidden input can't reasonably carry a whole
        base64 image back through the form on every save) with any newly
        uploaded ones (read from `files`, base64-encoded the same way
        every existing photo already is — see incident_report_docx.py's
        own use of this field for why base64-in-the-database instead of
        saved-to-disk: this app has no upload-to-disk path anywhere
        else, and a NOC report's occasional handful of photos doesn't
        justify building one)."""
        keep_ids = set(form.getlist("keep_picture_id"))
        kept = [p for p in existing_pictures if p.get("id") in keep_ids]

        new_pictures = []
        if files:
            for f in files.getlist("picture_reference"):
                if not f or not f.filename:
                    continue
                data = f.read()
                if not data:
                    continue
                data, content_type = IncidentReportService._normalize_image(data, f.content_type)
                new_pictures.append({
                    "id": str(uuid.uuid4()),
                    "filename": f.filename,
                    "content_type": content_type,
                    "data_base64": base64.b64encode(data).decode("ascii"),
                })
        return kept + new_pictures

    @staticmethod
    def _normalize_image(data, content_type):
        """Re-encodes an uploaded photo through Pillow into a plain RGB
        PNG before it's ever embedded in a DOCX/PDF — a real phone photo
        or screen-capture tool can produce an unusual color profile,
        palette mode, or EXIF rotation that python-docx's own image
        inspection (used to size the picture when only a width is given
        — see incident_report_docx.py's add_picture() calls) doesn't
        always handle the same way Word's PDF export path does; a
        production export failed with a generic Word COM error
        (ExportAsFixedFormat's own "unexpected error", no further
        detail) on a report with a real uploaded photo, which this is
        meant to prevent by normalizing every photo to a known-safe
        format up front rather than trusting whatever the browser
        upload happened to contain. Falls back to the original bytes
        unchanged if Pillow can't open it at all (rare — better to keep
        an odd-but-working upload than block it outright)."""
        try:
            from io import BytesIO as _BytesIO

            import pillow_heif
            from PIL import Image, ImageOps

            # Registers HEIC/HEIF with Pillow's Image.open() — Pillow has
            # no built-in HEIC support, and a phone camera's default
            # format IS HEIC (iPhone, and many Android phones). Without
            # this, Image.open() below raises on every HEIC upload, this
            # whole function falls through to the except below, and the
            # RAW undecoded HEIC bytes get embedded as-is — confirmed
            # live as the actual root cause of a VM PDF export failing
            # with a bare "Command failed" from Word (both
            # ExportAsFixedFormat AND the legacy SaveAs path) on a report
            # with an iPhone photo, even when done by hand in Word
            # directly, not just through this app's own automation: Word
            # can often still insert/display a HEIC image inline, but
            # whatever in its export/print pipeline tries to rasterize
            # it chokes with no further detail. Registering is cheap
            # and idempotent, so just doing it inline here rather than
            # once at import time keeps this self-contained.
            pillow_heif.register_heif_opener()

            image = Image.open(_BytesIO(data))
            image = ImageOps.exif_transpose(image)
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            buf = _BytesIO()
            image.save(buf, format="PNG")
            return buf.getvalue(), "image/png"
        except Exception:
            return data, content_type or "application/octet-stream"

    def create_report(self, fields):
        report_id = str(uuid.uuid4())
        self.repository.create(report_id, fields, self._now())
        return report_id

    def update_report(self, report_id, fields):
        return self.repository.update(report_id, fields, self._now())

    def delete_report(self, report_id):
        return self.repository.delete(report_id)

    def set_status(self, report_id, status):
        return self.repository.set_status(report_id, status, self._now())

    @staticmethod
    def is_complete(fields):
        """True if every required field (see _REQUIRED_FIELDS) is
        non-blank, there's at least one chronology event, every one of
        those events has its own date/time/description filled in —
        matching the `required` attributes on each event row's inputs
        (document.html) — and, only if has_second_fault is set, every
        one of _SECOND_FAULT_TEXT_FIELDS (issued_time plus the 5 "_2"
        fault fields) is filled in too (same "only required once it's
        actually there" logic as chronology events — a report with no
        second fault was never asked to fill these in, so it can't be
        blocked on them)."""
        if not all((fields.get(f) or "").strip() for f in _REQUIRED_FIELDS):
            return False
        events = json.loads(fields.get("chronology_events_json") or "[]")
        if not events:
            return False
        if not all(e.get("date") and e.get("time") and e.get("description") for e in events):
            return False
        if (fields.get("has_second_fault") or "").strip():
            if not all((fields.get(f) or "").strip() for f in _SECOND_FAULT_TEXT_FIELDS):
                return False
        return True

    def render_pdf(self, report_id, report=None):
        """`report`, if given (the route already needs it for the export
        filename), is used instead of fetching it again here."""
        report = report if report is not None else self.repository.get(report_id)
        return build_pdf(report) if report else None

    def render_docx(self, report_id, report=None):
        """`report`, if given (the route already needs it for the export
        filename), is used instead of fetching it again here."""
        report = report if report is not None else self.repository.get(report_id)
        return build_docx(report) if report else None

    @staticmethod
    def _now():
        return datetime.now(ZoneInfo(current_app.config["TIMEZONE"])).isoformat(timespec="seconds")
