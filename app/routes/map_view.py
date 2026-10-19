"""Map View page routes."""

import io
import re

from flask import Blueprint, Response, jsonify, render_template, request
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.services.map.map_view_service import MapViewService

# Same dark-navy header + solid-black grid as telegram_alert.py's own
# .xlsx export — kept as its own constants since this export doesn't
# need that module's banding/hyperlinks/priority rows.
_HEADER_FILL = PatternFill("solid", fgColor="FF1A3A5C")
_HEADER_FONT = Font(bold=True, size=12, color="FFFFFFFF")
_HEADER_ALIGNMENT = Alignment(horizontal="center", vertical="center", wrap_text=True)
_BORDER_SIDE = Side(style="medium", color="FF000000")
_BORDER = Border(left=_BORDER_SIDE, right=_BORDER_SIDE, top=_BORDER_SIDE, bottom=_BORDER_SIDE)

# Per-header data-cell tweaks — everything else keeps openpyxl's default
# alignment (left for text, right for numbers) and auto-sized width.
_CENTER_ALIGN_HEADERS = {"Site Code", "POP Code"}
_LEFT_ALIGN_HEADERS = {"Lat", "Lon"}
_NARROW_COLUMN_WIDTHS = {"Site Name": 18, "Status": 12, "Village": 14}

# Pastel tints of the map's own status dot colors (DOT_COLORS in
# map-view.js), readable against black text. Only the Status cell gets
# filled; only on_air/planned get a color, "other" stays uncolored.
_ON_AIR_ROW_FILL = PatternFill("solid", fgColor="FFD1FAE5")
_PLANNED_ROW_FILL = PatternFill("solid", fgColor="FFDBEAFE")


def _site_status_fill(row):
    status = row.get("status")
    if status == "on_air":
        return _ON_AIR_ROW_FILL
    if status == "planned":
        return _PLANNED_ROW_FILL
    return None


map_view_bp = Blueprint("mapview", __name__)
map_view_service = MapViewService()

# (dict key, column header) per sheet — export_xlsx() below writes one
# workbook with 3 sheets (map_view_export / Site down / Pop site) rather
# than 3 separate downloads.
_SITE_CSV_COLUMNS = [
    ("name", "Site Code"),
    ("site_name", "Site Name"),
    ("status", "Status"),
    ("site_grade", "Grade"),
    ("province", "Province"),
    ("district", "District"),
    ("commune", "Commune"),
    ("village", "Village"),
    ("nms", "NMS"),
    ("lat", "Lat"),
    ("lon", "Lon"),
]
_SITE_DOWN_CSV_COLUMNS = [
    ("name", "Site Code"),
    ("site_name", "Site Name"),
    ("incident_id", "Incident ID"),
    ("occurred_at", "Occurred At"),
    ("province", "Province"),
    ("district", "District"),
    ("commune", "Commune"),
    ("lat", "Lat"),
    ("lon", "Lon"),
]
_POP_CSV_COLUMNS = [
    ("code", "POP Code"),
    ("name", "POP Name"),
    ("type", "Type"),
    ("pro_owner", "Owner"),
    ("province", "Province"),
    ("district", "District"),
    ("commune", "Commune"),
    ("lat", "Lat"),
    ("lon", "Lon"),
]
# Boundary export — sites get their own Site Down flag column here
# (the main export uses a separate "Site down" sheet instead).
_BOUNDARY_SITE_CSV_COLUMNS = [
    ("name", "Site Code"),
    ("site_name", "Site Name"),
    ("status", "Status"),
    ("is_down", "Site Down"),
    ("province", "Province"),
    ("district", "District"),
    ("commune", "Commune"),
    ("lat", "Lat"),
    ("lon", "Lon"),
]

# Mirrors map-view.js's ON_AIR_NMS_FILTERS/matchesPopFilter —
# export_xlsx() filters to whatever the map's status dropdown is
# currently showing ("export what you're looking at").
_ON_AIR_NMS_FILTERS = {"on_air_nokia": "Nokia", "on_air_huawei": "Huawei", "on_air_zte": "ZTE"}
_ISP_FILTERS = {"pop_telcotech": "Telcotech", "pop_ezecom": "Ezecom"}
_FILTER_FILENAMES = {
    "all": "map_view_export",
    "on_air": "OnAir-site-mapview",
    "on_air_nokia": "Nokia-site-mapview",
    "on_air_huawei": "Huawei-site-mapview",
    "on_air_zte": "ZTE-site-mapview",
    "planned": "Planned-site-mapview",
    "other": "Other-site-mapview",
    "site_down": "SiteDown-site-mapview",
    "pop_telcotech": "ISP_TELCOTECH-mapview",
    "pop_ezecom": "ISP_EZECOM-mapview",
}


def _filter_export_rows(sites, pops, filter_key):
    """(sites, pops) narrowed to filter_key — an ISP owner filter hides
    every site and shows only that owner's POPs; any other non-"all"
    status filter hides POPs entirely, same as applyFilter() on the map."""
    if filter_key in _ISP_FILTERS:
        owner = _ISP_FILTERS[filter_key]
        return [], [p for p in pops if p.get("pro_owner") == owner]
    if not filter_key or filter_key == "all":
        return sites, pops
    if filter_key in _ON_AIR_NMS_FILTERS:
        vendor = _ON_AIR_NMS_FILTERS[filter_key]
        filtered = [s for s in sites if s.get("status") == "on_air" and s.get("nms") == vendor]
    elif filter_key == "site_down":
        filtered = [s for s in sites if s.get("is_down")]
    elif filter_key == "other":
        filtered = [s for s in sites if s.get("status") not in ("on_air", "planned")]
    elif filter_key in ("on_air", "planned"):
        filtered = [s for s in sites if s.get("status") == filter_key]
    else:
        filtered = sites
    return filtered, []


@map_view_bp.route("/")
def index():
    sites = map_view_service.get_sites()
    return render_template(
        "map/index.html",
        sites=sites,
        status_counts=map_view_service.get_status_counts(sites),
        pops=map_view_service.get_pops(),
    )


@map_view_bp.route("/sites.json")
def sites_json():
    """Polled by map-view.js to auto-refresh marker colors/counts in place
    (no page reload, so pan/zoom/search stay untouched) — reads the same
    already-synced caches as index() above."""
    sites = map_view_service.get_sites()
    return jsonify(
        sites=sites,
        status_counts=map_view_service.get_status_counts(sites),
        pops=map_view_service.get_pops(),
    )


def _write_xlsx_sheet(workbook, title, rows, columns, row_fill_fn=None, fill_headers=None):
    sheet = workbook.create_sheet(title=title)
    sheet.append([header for _, header in columns])
    for ci in range(1, len(columns) + 1):
        cell = sheet.cell(row=1, column=ci)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = _HEADER_ALIGNMENT
        cell.border = _BORDER
    sheet.row_dimensions[1].height = 26
    sheet.freeze_panes = "A2"

    # sheet.max_row isn't cached — using it per row here made this loop
    # O(n^2) and turned a ~4,300-row sheet into a 90+ second export.
    for row_idx, row in enumerate(rows, start=2):
        sheet.append([row.get(key, "") for key, _ in columns])
        fill = row_fill_fn(row) if row_fill_fn else None
        for ci, (_, header) in enumerate(columns, start=1):
            cell = sheet.cell(row=row_idx, column=ci)
            cell.border = _BORDER
            if fill and (not fill_headers or header in fill_headers):
                cell.fill = fill

    last_row = len(rows) + 1
    for ci, (key, header) in enumerate(columns, start=1):
        if header in _CENTER_ALIGN_HEADERS:
            align = Alignment(horizontal="center")
        elif header in _LEFT_ALIGN_HEADERS:
            align = Alignment(horizontal="left")
        else:
            align = None
        if align:
            for row_idx in range(2, last_row + 1):
                sheet.cell(row=row_idx, column=ci).alignment = align

        if header in _NARROW_COLUMN_WIDTHS:
            width = _NARROW_COLUMN_WIDTHS[header]
        else:
            max_len = max([len(header)] + [len(str(row.get(key, ""))) for row in rows])
            width = min(max(max_len + 4, 12), 60)
        sheet.column_dimensions[get_column_letter(ci)].width = width


@map_view_bp.route("/export.xlsx")
def export_xlsx():
    """One workbook, 3 sheets — every plotted Site, just the down ones,
    then every plotted POP — rather than 3 separate downloads. Narrowed to
    the active status filter (?filter=on_air_nokia etc., set by the
    Export button reading the map's own currentFilter) when one is
    active — see _filter_export_rows()."""
    filter_key = request.args.get("filter", "all")
    sites, pops = _filter_export_rows(map_view_service.get_sites(), map_view_service.get_pops(), filter_key)
    site_down = [s for s in sites if s.get("is_down")]

    workbook = Workbook()
    workbook.remove(workbook.active)  # drop openpyxl's default blank sheet
    _write_xlsx_sheet(
        workbook, "map_view_export", sites, _SITE_CSV_COLUMNS, row_fill_fn=_site_status_fill, fill_headers={"Status"}
    )
    _write_xlsx_sheet(workbook, "Site down", site_down, _SITE_DOWN_CSV_COLUMNS)
    _write_xlsx_sheet(workbook, "Pop site", pops, _POP_CSV_COLUMNS)

    buffer = io.BytesIO()
    workbook.save(buffer)
    filename = _FILTER_FILENAMES.get(filter_key, "map_view_export")
    return Response(
        buffer.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}.xlsx"},
    )


@map_view_bp.route("/export-boundary.xlsx", methods=["POST"])
def export_boundary_xlsx():
    """One workbook, 2 sheets, scoped to whichever province/district/commune
    boundary the user searched — the point-in-polygon test itself runs
    client-side (map-view.js already has the boundary GeoJSON loaded for
    drawing the shape), so this route just formats whatever site/POP rows
    it's handed rather than re-deriving them from a boundary name."""
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name") or "boundary")
    # Filter to dicts only — a malformed entry would otherwise throw on
    # .get() below and return an HTML error page named ".xlsx".
    boundary_sites = [s for s in (payload.get("sites") or []) if isinstance(s, dict)]
    boundary_pops = [p for p in (payload.get("pops") or []) if isinstance(p, dict)]
    for site in boundary_sites:
        site["is_down"] = "Yes" if site.get("is_down") else "No"

    # Excel sheet titles cap at 31 chars and reject : \ / ? * [ ].
    def sheet_title(text):
        return re.sub(r"[:\\/?*\[\]]", " ", text).strip()[:31] or "Sheet"

    workbook = Workbook()
    workbook.remove(workbook.active)
    _write_xlsx_sheet(
        workbook,
        sheet_title(f"{name} Site"),
        boundary_sites,
        _BOUNDARY_SITE_CSV_COLUMNS,
        row_fill_fn=_site_status_fill,
        fill_headers={"Status"},
    )
    _write_xlsx_sheet(workbook, sheet_title(f"{name} ISP Site"), boundary_pops, _POP_CSV_COLUMNS)

    buffer = io.BytesIO()
    workbook.save(buffer)
    safe_name = "".join(c if c.isalnum() else "_" for c in name).strip("_") or "boundary"
    return Response(
        buffer.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={safe_name}_site_by_province.xlsx"},
    )
