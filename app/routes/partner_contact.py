"""Partner Contact page — reads from the local partner_contact_cache,
kept in sync every PARTNER_CONTACT_SYNC_INTERVAL_SECONDS.
Create/Add Contact/Edit/Delete write straight to MSSQL via
PartnerContactService, then call _resync_now() to refresh the cache
immediately so the change isn't invisible until the next scheduled sync."""

import csv
import getpass
import io
import threading

from flask import Blueprint, Response, current_app, jsonify, redirect, render_template, request, send_file, url_for
from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from app.database.cache import PARTNER_CONTACT_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository
from app.services.partner_contact.partner_contact_service import PartnerContactService
from app.services.partner_contact.partner_contact_sync_service import PartnerContactSyncService
from app.utils.logger import get_logger

logger = get_logger(__name__)

partner_contact_bp = Blueprint("partner_contact", __name__)

# Same fallback as dashboard.py's _DEFAULT_ACK_USERNAME — pre-fills
# "Your Name" before the browser has cached a real name.
_DEFAULT_ACK_USERNAME = getpass.getuser()

_TABLE = PARTNER_CONTACT_CACHE_TABLES[0]

_CSV_COLUMNS = (
    ("partner_name", "Partner Name"),
    ("partner_type", "Partner Type"),
    ("domain", "Domain"),
    ("escalation_level", "Escalation Level"),
    ("escalation_matrix", "Escalation Matrix"),
    ("contact_name", "Contact Name"),
    ("contact_role", "Contact Role"),
    ("phone_number", "Phone Number"),
    ("email", "Email"),
    ("remark", "Remark"),
    ("created_by", "Created By"),
    ("created_at", "Created At"),
    ("updated_by", "Updated By"),
    ("updated_at", "Updated At"),
)


# Column order for the Import template/upload — same fields as the Add
# Partner/Add Contact form, but without the audit columns _CSV_COLUMNS
# (Export) carries, since those are system-written, not user-filled.
_IMPORT_COLUMNS = (
    ("partner_name", "Partner Name"),
    ("partner_type", "Partner Type"),
    ("domain", "Domain"),
    ("escalation_level", "Escalation Level"),
    ("escalation_matrix", "Escalation Matrix"),
    ("contact_name", "Contact Name"),
    ("contact_role", "Contact Role"),
    ("phone_number", "Phone Number"),
    ("email", "Email"),
    ("remark", "Remark"),
)

_IMPORT_REQUIRED = (
    "partner_name", "partner_type", "domain",
    "escalation_level", "escalation_matrix",
    "contact_name", "contact_role", "phone_number", "email",
)


class _CacheRepo(BaseCacheRepository):
    valid_tables = PARTNER_CONTACT_CACHE_TABLES
    columns = tuple(key for key, _ in _CSV_COLUMNS)
    order_by = "partner_type, partner_name"


_repo = _CacheRepo()
_service = PartnerContactService()
_sync_service = PartnerContactSyncService()


def _resync_now():
    """Refreshes the local cache from MSSQL synchronously, right after a
    Create/Edit/Delete, instead of waiting for the next scheduled sync.
    sync() already logs and swallows its own errors, so a slow/unreachable
    MSSQL just leaves the cache to catch up next cycle."""
    _sync_service.sync()


def _resync_async():
    """Same effect as _resync_now(), but doesn't make the caller wait for
    it — used by the split-panel's rapid "click New, click New" JSON
    endpoints (*-only routes below), where a full MSSQL re-query-and-
    rewrite-the-whole-cache-table on every single click (measured ~0.5s
    each, confirmed live) was the actual cause of it feeling slow, not
    the write itself. Safe to skip waiting here specifically because the
    caller (partner_contact.js) already renders the new/changed row
    straight from this response — it doesn't need the cache to be fresh
    for ITS OWN view; the cache still catches up within about a second,
    well before the page-reload-on-Close (see closePartnerModal, JS)
    would ever read it. The old redirect-based routes below (create/
    add_contact/update/delete) deliberately keep the synchronous
    _resync_now() — they navigate to a freshly rendered page immediately,
    which DOES need the cache caught up by then."""
    app = current_app._get_current_object()

    def _run():
        with app.app_context():
            _sync_service.sync()

    threading.Thread(target=_run, daemon=True).start()


@partner_contact_bp.route("/partner-contact")
def index():
    rows = _repo.fetch_all(_TABLE)
    # Distinct domains present (e.g. "Telcotech"/"Cellcard") for
    # index.html's domain tabs — client-side filter, not a query param,
    # same as the search box.
    domains = sorted({r["domain"] for r in rows if r.get("domain")})

    return render_template(
        "partner_contact/index.html",
        rows=rows,
        domains=domains,
        default_ack_username=_DEFAULT_ACK_USERNAME,
    )


@partner_contact_bp.route("/partner-contact/export.csv")
def export_csv():
    rows = _repo.fetch_all(_TABLE)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header for _, header in _CSV_COLUMNS)
    for row in rows:
        writer.writerow(row.get(key, "") for key, _ in _CSV_COLUMNS)
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=partner_contact.csv"},
    )



@partner_contact_bp.route("/partner-contact/partner-contacts")
def partner_contacts():
    """Feeds the split panel's mini-table when "Add Contact" opens on a
    partner that already has Contacts — without this, clicking Add
    Contact on a partner with e.g. 5 existing Contacts would start the
    list empty, hiding what's already there. Reads the local cache (same
    as index()), not a live MSSQL query — this is a read, no write."""
    partner_id = request.args.get("partner_id", "").strip()
    if not partner_id:
        return jsonify(contacts=[])
    rows = _repo.fetch_all(_TABLE)
    contacts = [
        {
            "contact_id": r.get("contact_id"),
            "escalation_level": r.get("escalation_level") or "",
            "escalation_matrix": r.get("escalation_matrix") or "",
            "contact_name": r.get("contact_name") or "",
            "contact_role": r.get("contact_role") or "",
            "phone_number": r.get("phone_number") or "",
            "email": r.get("email") or "",
            "remark": r.get("remark") or "",
        }
        for r in rows
        if r.get("partner_id") == partner_id and r.get("contact_id")
    ]
    return jsonify(contacts=contacts)


@partner_contact_bp.route("/partner-contact/domains")
def domains():
    """Feeds the Add Partner modal's Domain field dropdown-card (index.html's
    #pcDomainDropdown, wired up in partner_contact.js) — every distinct
    Domain value already in use (e.g. "Telcotech"/"Cellcard"), sorted
    case-insensitively, so it can be picked from a dropdown instead of
    retyped by hand. Domain stays a real <input> — this isn't a closed
    list, typing a genuinely new Domain by hand still works exactly the
    same. Reads the local cache (already synced), not a live MSSQL query."""
    rows = _repo.fetch_all(_TABLE)
    values = {(r.get("domain") or "").strip() for r in rows}
    values.discard("")
    return jsonify(domains=sorted(values, key=str.lower))


@partner_contact_bp.route("/partner-contact/escalation-levels")
def escalation_levels():
    """Feeds the Add Partner/Add Contact modal's Escalation Level
    dropdown-card — same idea as domains() above, every distinct
    Escalation Level value already in use (e.g. "L1"/"Level1"), sorted
    case-insensitively. Still a real <input>, not a closed list — typing
    a genuinely new value by hand works exactly the same as before."""
    rows = _repo.fetch_all(_TABLE)
    values = {(r.get("escalation_level") or "").strip() for r in rows}
    values.discard("")
    return jsonify(escalation_levels=sorted(values, key=str.lower))


@partner_contact_bp.route("/partner-contact/escalation-matrix-values")
def escalation_matrix_values():
    """Feeds the Add Partner/Add Contact modal's Escalation Matrix
    dropdown-card — same idea as escalation_levels() above, every
    distinct Escalation Matrix value already in use (e.g. "NOC ->
    Manager"), sorted case-insensitively. Still a real <input>, not a
    closed list — typing a genuinely new value by hand works exactly
    the same as before."""
    rows = _repo.fetch_all(_TABLE)
    values = {(r.get("escalation_matrix") or "").strip() for r in rows}
    values.discard("")
    return jsonify(escalation_matrix_values=sorted(values, key=str.lower))


@partner_contact_bp.route("/partner-contact/check-name")
def check_name():
    """Live duplicate check for the Add Partner modal's Partner Name field
    — called from partner_contact.js as the user types (debounced), so the
    "this name already exists" hint shows up front instead of only after
    submitting. Same partner_name_exists() the create() route itself
    checks, so this preview can never disagree with what submit does."""
    partner_name = request.args.get("name", "").strip()
    exists = bool(partner_name) and _service.partner_name_exists(partner_name)
    return jsonify(exists=exists)


@partner_contact_bp.route("/partner-contact/import-template.xlsx")
def import_template():
    """Downloadable starting point for the Import button — one row per
    Contact, same Partner Name repeated across rows groups those Contacts
    under one Partner (see import_rows() below). The tip comment on the
    Partner Name header (hover the small red corner) is the only place
    the "partner already existed" rule is documented, since the import
    itself only surfaces it via the after-upload popup, not per row."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Import"

    header_fill = PatternFill(start_color="1F2937", end_color="1F2937", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    for col_idx, (_, header) in enumerate(_IMPORT_COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.fill = header_fill
        cell.font = header_font
        ws.column_dimensions[get_column_letter(col_idx)].width = 24

    ws.cell(row=1, column=1).comment = Comment(
        "If Partner Name already exists, it will NOT be created again — "
        "only the Contact rows below will be added under the existing partner.",
        "NOC Dashboard",
        width=260,
        height=90,
    )

    example_rows = [
        ("Telcotech", "ISP", "Telcotech", "L1", "NOC -> Manager",
         "Sok Dara", "NOC Manager", "+855 12 345 678", "dara@telcotech.com",
         "Primary contact for peering issues"),
        ("Telcotech", "ISP", "Telcotech", "L2", "NOC -> Manager -> Director",
         "Chan Vuthy", "Escalation Manager", "+855 12 999 111", "vuthy@telcotech.com",
         "Escalate here if L1 no response 30min"),
    ]
    for row_idx, row in enumerate(example_rows, start=2):
        for col_idx, value in enumerate(row, start=1):
            ws.cell(row=row_idx, column=col_idx, value=value)

    # Domain/Escalation Level get a dropdown of every value already in
    # use (same lists domains()/escalation_levels() feed the web form's
    # own dropdown-cards with) — but showErrorMessage=False means Excel
    # never blocks or warns on a typed value outside the list, so it's
    # still a free-text cell, the dropdown is just a shortcut. Values
    # live on a hidden helper sheet since a plain comma list is capped
    # at 255 characters and would silently truncate once enough
    # distinct domains/levels exist.
    rows = _repo.fetch_all(_TABLE)
    domain_values = sorted({(r.get("domain") or "").strip() for r in rows if r.get("domain")}, key=str.lower)
    escalation_level_values = sorted(
        {(r.get("escalation_level") or "").strip() for r in rows if r.get("escalation_level")}, key=str.lower
    )
    last_row = max(len(example_rows) + 1, 500)
    if domain_values or escalation_level_values:
        lists_ws = wb.create_sheet("Lists")
        lists_ws.sheet_state = "hidden"
        for i, value in enumerate(domain_values, start=1):
            lists_ws.cell(row=i, column=1, value=value)
        for i, value in enumerate(escalation_level_values, start=1):
            lists_ws.cell(row=i, column=2, value=value)

        domain_col = get_column_letter([key for key, _ in _IMPORT_COLUMNS].index("domain") + 1)
        level_col = get_column_letter([key for key, _ in _IMPORT_COLUMNS].index("escalation_level") + 1)
        if domain_values:
            dv = DataValidation(
                type="list",
                formula1=f"Lists!$A$1:$A${len(domain_values)}",
                allow_blank=True,
                showDropDown=False,
                showErrorMessage=False,
            )
            ws.add_data_validation(dv)
            dv.add(f"{domain_col}2:{domain_col}{last_row}")
        if escalation_level_values:
            dv = DataValidation(
                type="list",
                formula1=f"Lists!$B$1:$B${len(escalation_level_values)}",
                allow_blank=True,
                showDropDown=False,
                showErrorMessage=False,
            )
            ws.add_data_validation(dv)
            dv.add(f"{level_col}2:{level_col}{last_row}")

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name="partner_contact_import_template.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _parse_import_file(file_storage):
    """Reads either .xlsx (openpyxl) or .csv (stdlib csv) into a list of
    raw row tuples, header row skipped, fully-blank rows dropped. Column
    ORDER must match _IMPORT_COLUMNS — values are zipped positionally,
    not matched by header text, same assumption the CSV export makes.

    Raises ValueError on anything not actually a readable .xlsx/.csv
    (wrong file type, corrupted file, a renamed extension) — import_rows()
    below turns that into a clean "unreadable file" response instead of
    the 500 this used to crash with."""
    filename = (file_storage.filename or "").lower()
    rows = []
    if filename.endswith(".xlsx"):
        try:
            wb = load_workbook(file_storage, data_only=True)
        except Exception as e:
            raise ValueError("not a readable .xlsx file") from e
        ws = wb.active
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row is None or all(v is None or str(v).strip() == "" for v in row):
                continue
            rows.append(row)
    elif filename.endswith(".csv"):
        try:
            text = file_storage.read().decode("utf-8-sig")
        except UnicodeDecodeError as e:
            raise ValueError("not a readable .csv file") from e
        reader = csv.reader(io.StringIO(text))
        next(reader, None)
        for row in reader:
            if not any((v or "").strip() for v in row):
                continue
            rows.append(row)
    else:
        raise ValueError("unsupported file type — use .xlsx or .csv")
    return rows


@partner_contact_bp.route("/partner-contact/verify-import-password", methods=["POST"])
def verify_import_password():
    """Checked by the Import password modal before it reveals the
    "Choose File" step (partner_contact.js). The password itself only
    ever lives here server-side — the browser holds what the user
    typed, not the value it's compared against."""
    password = request.form.get("password", "")
    ok = password == current_app.config["PARTNER_CONTACT_IMPORT_PASSWORD"]
    return jsonify(ok=ok)


@partner_contact_bp.route("/partner-contact/import", methods=["POST"])
def import_rows():
    """Bulk-import target for the Import button. Rows sharing the same
    Partner Name (case-insensitive) are grouped into one Partner with
    several Contacts. Only Partner Name is checked for duplicates — if it
    already exists, that Partner is NOT created again, its Contacts are
    just attached to the existing one (see partner_contact_service's
    find_partner_id_by_name). Contacts themselves are never de-duplicated,
    same as every other write path in this file. A row missing any
    required field is skipped and reported back, not silently dropped.

    Also re-checks the import password (see verify_import_password above)
    so the gate can't be skipped by calling this endpoint directly."""
    if request.form.get("import_password", "") != current_app.config["PARTNER_CONTACT_IMPORT_PASSWORD"]:
        return jsonify(ok=False, error="bad_password")

    file = request.files.get("file")
    username = request.form.get("username", "").strip()
    if not file or not file.filename:
        return jsonify(ok=False, error="no_file")

    keys = [key for key, _ in _IMPORT_COLUMNS]
    try:
        raw_rows = _parse_import_file(file)
    except ValueError as e:
        logger.warning("Partner Contact import: unreadable file %s (%s)", file.filename, e)
        return jsonify(ok=False, error="unreadable_file")

    groups = {}
    order = []
    failed_rows = []

    for idx, raw in enumerate(raw_rows, start=2):
        values = list(raw) + [""] * (len(keys) - len(raw))
        record = {k: ("" if v is None else str(v).strip()) for k, v in zip(keys, values)}
        missing = [k for k in _IMPORT_REQUIRED if not record.get(k)]
        if missing:
            failed_rows.append({"row": idx, "reason": "missing " + ", ".join(missing)})
            continue

        norm_name = record["partner_name"].upper()
        if norm_name not in groups:
            groups[norm_name] = {
                "partner_name": record["partner_name"],
                "partner_type": record["partner_type"],
                "domain": record["domain"],
                "contacts": [],
            }
            order.append(norm_name)
        groups[norm_name]["contacts"].append({
            "escalation_level": record["escalation_level"],
            "escalation_matrix": record["escalation_matrix"],
            "contact_name": record["contact_name"],
            "contact_role": record["contact_role"],
            "phone_number": record["phone_number"],
            "email": record["email"],
            "remark": record.get("remark", ""),
        })

    partners_created = 0
    contacts_added = 0
    existing_partners = []

    for norm_name in order:
        group = groups[norm_name]
        existing_id = _service.find_partner_id_by_name(group["partner_name"])
        if existing_id:
            existing_partners.append(group["partner_name"])
            for c in group["contacts"]:
                added = _service.add_contact(partner_id=existing_id, username=username, **c)
                if added:
                    contacts_added += 1
        else:
            _service.create_partner_with_contacts(
                partner_name=group["partner_name"],
                partner_type=group["partner_type"],
                domain=group["domain"],
                username=username,
                contacts=group["contacts"],
            )
            partners_created += 1
            contacts_added += len(group["contacts"])

    if partners_created or contacts_added:
        _resync_now()

    return jsonify(
        ok=True,
        partners_created=partners_created,
        contacts_added=contacts_added,
        existing_partners=existing_partners,
        failed_rows=failed_rows,
    )


@partner_contact_bp.route("/partner-contact/create-partner-only", methods=["POST"])
def create_partner_only():
    """"New" button target in the Add Partner modal's split-panel flow
    (see partner_contact.js) — saves just the Partner row (Name/Type/
    Domain), no Contact yet, via create_partner_with_contacts() with an
    empty contacts list (that function already handles zero contacts
    fine — see PartnerContactRepository.create_partner_with_contacts).
    Returns JSON, not a redirect — called via fetch(), not a normal form
    navigation, so the modal can switch into its two-column "add contact
    after contact" layout right after without leaving the page."""
    partner_name = request.form.get("partner_name", "").strip()
    partner_type = request.form.get("partner_type", "").strip()
    domain = request.form.get("domain", "").strip()
    username = request.form.get("username", "").strip()

    if not (partner_name and partner_type and domain and username):
        return jsonify(ok=False, error="missing_fields")
    if _service.partner_name_exists(partner_name):
        return jsonify(ok=False, error="duplicate")

    partner_id = _service.create_partner_with_contacts(
        partner_name=partner_name,
        partner_type=partner_type,
        domain=domain,
        username=username,
        contacts=[],
    )
    _resync_async()
    return jsonify(
        ok=True,
        partner_id=partner_id,
        partner_name=partner_name,
        partner_type=partner_type,
        domain=domain,
    )


@partner_contact_bp.route("/partner-contact/add-contact-only", methods=["POST"])
def add_contact_only():
    """Split-panel "Save Contact" target — same write as add_contact()
    below (add_contact() never creates a new Partner row, see its own
    docstring), but returns JSON instead of redirecting, so
    partner_contact.js can append a row to the modal's live mini-table
    and clear the form for the next contact instead of navigating away —
    lets several contacts get added back-to-back without leaving the
    modal, unlike add_contact()'s reopen-on-redirect round trip."""
    partner_id = request.form.get("partner_id", "").strip()
    username = request.form.get("username", "").strip()
    escalation_level = request.form.get("escalation_level", "").strip()
    escalation_matrix = request.form.get("escalation_matrix", "").strip()
    contact_name = request.form.get("contact_name", "").strip()
    contact_role = request.form.get("contact_role", "").strip()
    phone_number = request.form.get("phone_number", "").strip()
    email = request.form.get("email", "").strip()
    remark = request.form.get("remark", "").strip()

    if not (
        partner_id and username and contact_name and contact_role
        and phone_number and email
    ):
        return jsonify(ok=False, error="missing_fields")

    added = _service.add_contact(
        partner_id=partner_id,
        escalation_level=escalation_level,
        escalation_matrix=escalation_matrix,
        contact_name=contact_name,
        contact_role=contact_role,
        phone_number=phone_number,
        email=email,
        remark=remark,
        username=username,
    )
    if not added:
        return jsonify(ok=False, error="failed")
    _resync_async()
    return jsonify(
        ok=True,
        contact_id=str(added["ContactID"]),
        escalation_level=escalation_level,
        escalation_matrix=escalation_matrix,
        contact_name=contact_name,
        contact_role=contact_role,
        phone_number=phone_number,
        email=email,
        remark=remark,
    )


@partner_contact_bp.route("/partner-contact/update-contact-only", methods=["POST"])
def update_contact_only():
    """Split-panel mini-table's Edit target — same write as update()
    below, but returns JSON instead of redirecting, so
    partner_contact.js can refresh that one row in place instead of
    leaving the modal. partner_name/partner_type ride along unchanged
    (locked read-only in split mode — see pcEnterSplitMode()) since
    update_partner() writes both Partner and Contact fields together."""
    partner_id = request.form.get("partner_id", "").strip()
    contact_id = request.form.get("contact_id", "").strip()
    partner_name = request.form.get("partner_name", "").strip()
    partner_type = request.form.get("partner_type", "").strip()
    username = request.form.get("username", "").strip()
    escalation_level = request.form.get("escalation_level", "").strip()
    escalation_matrix = request.form.get("escalation_matrix", "").strip()
    contact_name = request.form.get("contact_name", "").strip()
    contact_role = request.form.get("contact_role", "").strip()
    phone_number = request.form.get("phone_number", "").strip()
    email = request.form.get("email", "").strip()
    remark = request.form.get("remark", "").strip()

    if not (
        partner_id and contact_id and partner_name and partner_type and username
        and contact_name and contact_role and phone_number and email
    ):
        return jsonify(ok=False, error="missing_fields")

    updated = _service.update_partner(
        partner_id=partner_id,
        contact_id=contact_id,
        partner_name=partner_name,
        partner_type=partner_type,
        escalation_level=escalation_level,
        escalation_matrix=escalation_matrix,
        contact_name=contact_name,
        contact_role=contact_role,
        phone_number=phone_number,
        email=email,
        remark=remark,
        username=username,
    )
    if not updated:
        return jsonify(ok=False, error="failed")
    _resync_async()
    return jsonify(
        ok=True,
        contact_id=contact_id,
        escalation_level=escalation_level,
        escalation_matrix=escalation_matrix,
        contact_name=contact_name,
        contact_role=contact_role,
        phone_number=phone_number,
        email=email,
        remark=remark,
    )


@partner_contact_bp.route("/partner-contact/delete-contact-only", methods=["POST"])
def delete_contact_only():
    """Split-panel mini-table's X target — same write as delete() below,
    but returns JSON instead of redirecting, so partner_contact.js can
    remove that one row from the live list instead of leaving the modal."""
    contact_id = request.form.get("contact_id", "").strip()
    if not (contact_id and _service.delete_contact(contact_id)):
        return jsonify(ok=False)
    _resync_async()
    return jsonify(ok=True)


@partner_contact_bp.route("/partner-contact/create", methods=["POST"])
def create():
    """Add Partner modal submit target — writes a new Partner plus its
    first Contact to MSSQL as one atomic batch via
    create_partner_with_contacts(), then resyncs the cache. `domain`
    (e.g. "Telcotech"/"Cellcard") is required — TBL_PARTNER.Domain is
    NOT NULL with no default in MSSQL. `username` is captured
    client-side only (no login system). To add another contact to this
    partner afterward, use add_contact() below instead of resubmitting
    this form."""
    partner_name = request.form.get("partner_name", "").strip()
    partner_type = request.form.get("partner_type", "").strip()
    domain = request.form.get("domain", "").strip()
    username = request.form.get("username", "").strip()
    escalation_level = request.form.get("escalation_level", "").strip()
    escalation_matrix = request.form.get("escalation_matrix", "").strip()
    contact_name = request.form.get("contact_name", "").strip()
    contact_role = request.form.get("contact_role", "").strip()
    phone_number = request.form.get("phone_number", "").strip()
    email = request.form.get("email", "").strip()
    remark = request.form.get("remark", "").strip()

    fields_filled = (
        partner_name and partner_type and domain and username
        and contact_name and contact_role and phone_number
        and email
    )

    status = "error"
    if fields_filled and _service.partner_name_exists(partner_name):
        status = "duplicate"
    elif fields_filled:
        created = _service.create_partner_with_contacts(
            partner_name=partner_name,
            partner_type=partner_type,
            domain=domain,
            username=username,
            contacts=[{
                "escalation_level": escalation_level,
                "escalation_matrix": escalation_matrix,
                "contact_name": contact_name,
                "contact_role": contact_role,
                "phone_number": phone_number,
                "email": email,
                "remark": remark,
            }],
        )
        if created:
            _resync_now()
            status = "created"
    return redirect(url_for("partner_contact.index", status=status))


@partner_contact_bp.route("/partner-contact/add-contact", methods=["POST"])
def add_contact():
    """Add Contact modal submit target — attaches a new Contact to the
    existing Partner the clicked row belongs to, via
    PartnerContactService.add_contact(); never creates a new Partner row.

    On success, partner_id/name/type ride along as redirect query params
    — index.html's script uses them to auto-reopen this same modal,
    pre-filled, so adding several contacts doesn't need re-finding the row."""
    partner_id = request.form.get("partner_id", "").strip()
    partner_name = request.form.get("partner_name", "").strip()
    partner_type = request.form.get("partner_type", "").strip()
    username = request.form.get("username", "").strip()
    escalation_level = request.form.get("escalation_level", "").strip()
    escalation_matrix = request.form.get("escalation_matrix", "").strip()
    contact_name = request.form.get("contact_name", "").strip()
    contact_role = request.form.get("contact_role", "").strip()
    phone_number = request.form.get("phone_number", "").strip()
    email = request.form.get("email", "").strip()
    remark = request.form.get("remark", "").strip()

    status = "error"
    if (
        partner_id and username
        and contact_name and contact_role and phone_number
        and email
    ):
        added = _service.add_contact(
            partner_id=partner_id,
            escalation_level=escalation_level,
            escalation_matrix=escalation_matrix,
            contact_name=contact_name,
            contact_role=contact_role,
            phone_number=phone_number,
            email=email,
            remark=remark,
            username=username,
        )
        if added:
            _resync_now()
            status = "contact_added"
            return redirect(url_for(
                "partner_contact.index",
                status=status,
                partner_id=partner_id,
                partner_name=partner_name,
                partner_type=partner_type,
            ))
    return redirect(url_for("partner_contact.index", status=status))


@partner_contact_bp.route("/partner-contact/update", methods=["POST"])
def update():
    """Edit modal submit target — writes to MSSQL via
    update_partner(), matched by partner_id/contact_id, not name/type
    text (which can itself change)."""
    partner_id = request.form.get("partner_id", "").strip()
    contact_id = request.form.get("contact_id", "").strip()
    partner_name = request.form.get("partner_name", "").strip()
    partner_type = request.form.get("partner_type", "").strip()
    username = request.form.get("username", "").strip()
    escalation_level = request.form.get("escalation_level", "").strip()
    escalation_matrix = request.form.get("escalation_matrix", "").strip()
    contact_name = request.form.get("contact_name", "").strip()
    contact_role = request.form.get("contact_role", "").strip()
    phone_number = request.form.get("phone_number", "").strip()
    email = request.form.get("email", "").strip()
    remark = request.form.get("remark", "").strip()

    status = "error"
    if (
        partner_id and contact_id and partner_name and partner_type and username
        and contact_name and contact_role and phone_number
        and email
    ):
        updated = _service.update_partner(
            partner_id=partner_id,
            contact_id=contact_id,
            partner_name=partner_name,
            partner_type=partner_type,
            escalation_level=escalation_level,
            escalation_matrix=escalation_matrix,
            contact_name=contact_name,
            contact_role=contact_role,
            phone_number=phone_number,
            email=email,
            remark=remark,
            username=username,
        )
        if updated:
            _resync_now()
            status = "updated"
    return redirect(url_for("partner_contact.index", status=status))


@partner_contact_bp.route("/partner-contact/delete", methods=["POST"])
def delete():
    """Delete button submit target — removes just this Contact row from
    MSSQL; the Partner row and its other contacts are untouched."""
    contact_id = request.form.get("contact_id", "").strip()
    status = "error"
    if contact_id and _service.delete_contact(contact_id):
        _resync_now()
        status = "deleted"
    return redirect(url_for("partner_contact.index", status=status))
