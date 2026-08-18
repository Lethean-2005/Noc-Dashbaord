"""Sends a Telegram alert listing every Incident Site Down whose outage has
passed ALERT_THRESHOLD_MIN (default 240 minutes / 4 hours), rendered as a
table image (via Pillow) rather than a plain text message — sent as a
document so Telegram doesn't recompress it and blur the text. Every send
also attaches a second document: the same rows as a styled .xlsx (via
openpyxl) — the image stays the at-a-glance view, the Excel file is the
"open this in a spreadsheet" copy. Same pattern shared by all 4 Telegram
alerts, see _build_excel_bytes()/_send_telegram_excel() below.

Reads the already-synced incident_site_down cache (see
app/repositories/incident/incident_site_down_cache_repository.py,
app/database/queries/incident_site_down.sql) instead of querying Postgres directly —
that cache is kept fresh every INCIDENT_SYNC_INTERVAL_SECONDS (default 5
min) by app/services/incident/incident_sync_service.py, which is more than
fresh enough for an alert that only checks every ALERT_INTERVAL_SECONDS
(default 4h), and it means this alert no longer runs its own independent
query against a table already prone to "conflict with recovery". Every row
read is also written into the local telegram_alert_cache table
(instance/localstorage.db, see
app/repositories/telegram/telegram_alert_cache_repository.py) before the
threshold filter below runs, so the alert's last run is inspectable
independent of whether anything was actually over-threshold. Never runs
unless TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_IDS are set in .env.

start() runs this on a background loop, once every ALERT_INTERVAL_SECONDS
(default 14400s / 4 hours) — called once from app/__init__.py::create_app().
The first send is timed to land on a clean clock boundary in the
deployment's TIMEZONE (e.g. 14400s -> 00:00, 04:00, 08:00, 12:00, 16:00,
20:00) rather than "4 hours after whenever the app happened to start" —
see _seconds_until_next_aligned_time(). This also means restarting the dev
server (which happens often) can't immediately resend an alert, since the
next aligned time is never right now.
"""

import io
import os
from datetime import datetime

import requests
from flask import current_app

from app.repositories.incident.incident_site_down_cache_repository import (
    IncidentSiteDownCacheRepository,
)
from app.repositories.telegram.telegram_alert_cache_repository import TelegramAlertCacheRepository
from app.services.scheduler_utils import seconds_until_next_aligned_time, start_singleton_loop
from app.utils.datetime import elapsed_minutes
from app.utils.logger import get_logger

try:
    from PIL import Image, ImageDraw, ImageFont

    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    _HAS_OPENPYXL = True
except ImportError:
    _HAS_OPENPYXL = False

logger = get_logger(__name__)

_TELEGRAM_SEND_MESSAGE_URL = "https://api.telegram.org/bot{token}/sendMessage"
_TELEGRAM_SEND_DOCUMENT_URL = "https://api.telegram.org/bot{token}/sendDocument"
_EXCEL_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# app/static/fonts/ (see base.html) — same Exo 2 family used across the
# dashboard's own UI, so the alert image looks consistent with the app.
_FONT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "static", "fonts")
_FONT_BOLD_PATH = os.path.join(_FONT_DIR, "Exo2-Bold.ttf")

# Excel styling — matches the PNG tables' own color choices (HEADER_BG,
# _PRIORITY_ROW_BG) so the .xlsx attachment reads as the same alert, not a
# differently-branded dump of the same data. Border is solid black (not a
# light grey) and the row font is sized up from openpyxl's 11pt default —
# both per explicit request, so the sheet reads as a clean, high-contrast
# printed table rather than a default spreadsheet dump.
_EXCEL_HEADER_ARGB = "FF1A3A5C"
_EXCEL_ALT_ROW_ARGB = "FFF5F7FA"
_EXCEL_PRIORITY_ARGB = "FFFFCDD2"
_EXCEL_BORDER_ARGB = "FF000000"
_EXCEL_TITLE_FONT_SIZE = 16
_EXCEL_HEADER_FONT_SIZE = 12
_EXCEL_DATA_FONT_SIZE = 12
_EXCEL_DATA_ROW_HEIGHT = 20


def _chat_ids(raw):
    """'-100123, -100456,' -> ['-100123', '-100456'] — tolerates blank
    entries from a trailing comma or extra whitespace."""
    return [chat_id.strip() for chat_id in raw.split(",") if chat_id.strip()]


def _cache_telegram_rows(rows, cache_repository):
    """Mirror every fetched row into telegram_alert_cache, same
    replace-everything pattern every other cache table in this project
    uses. Best-effort — a cache write failure shouldn't stop the alert
    itself from being evaluated/sent."""
    cache_repository = cache_repository or TelegramAlertCacheRepository()
    try:
        cache_repository.replace_all("telegram_alert_cache", rows)
    except Exception as e:
        logger.error(f"telegram_alert_cache write failed: {e}")


def _site_down_over_threshold(
    threshold_min, incident_site_down_cache_repository=None, cache_repository=None
):
    """Every Site Down incident not yet Closed whose alarm hasn't cleared
    (per incident_site_down.sql), read from the already-synced incident_site_down
    cache, and whose outage has passed `threshold_min` minutes, longest-
    outage first. outage_min is computed for every row (not just the ones
    over threshold) before caching, so telegram_alert_cache always has each
    incident's current outage duration — see _cache_telegram_rows()."""
    incident_site_down_cache_repository = (
        incident_site_down_cache_repository or IncidentSiteDownCacheRepository()
    )
    rows = incident_site_down_cache_repository.fetch_all("incident_site_down")
    for row in rows:
        row["outage_min"] = elapsed_minutes(row.get("occurred_at"))
    _cache_telegram_rows(rows, cache_repository)

    over_threshold = [row for row in rows if row["outage_min"] >= threshold_min]
    over_threshold.sort(key=lambda row: row["outage_min"], reverse=True)
    return over_threshold


def _format_outage(minutes):
    hours, mins = divmod(minutes, 60)
    return f"{hours}h:{mins:02d}"


def _format_message(rows, threshold_min):
    """Plain-text fallback, used only if Pillow/the font can't render an
    image (e.g. a stripped-down deploy without Pillow installed)."""
    hours = threshold_min // 60
    lines = [f"Incident Site Down — outage over {hours}h ({len(rows)})", ""]
    for row in rows:
        site = row.get("site_name") or row.get("site_code") or "Unknown site"
        lines.append(
            f"• {row.get('incident_id')} — {site} "
            f"— {_format_outage(row['outage_min'])} — {row.get('province') or 'Unknown province'}"
        )
    return "\n".join(lines)


def _wrap_text_px(text, font, max_px):
    """Wrap `text` to fit `max_px` width using `font`, word by word."""
    if not text:
        return [""]
    words = text.split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}" if current else word
        if font.getlength(candidate) > max_px and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def _render_table_image(rows, title):
    """Render `rows` as a "Site Down Alerts" table image, matching the
    dashboard's own dark-navy-header table style. Returns PNG bytes, or None
    if Pillow/the font isn't available (caller falls back to plain text)."""
    if not _HAS_PIL or not os.path.exists(_FONT_BOLD_PATH):
        return None

    SCALE = 2  # render at 2x, so text stays sharp after Telegram displays it
    FONT_SIZE, TITLE_SIZE = 28 * SCALE, 34 * SCALE
    CELL_PAD_X, CELL_PAD_Y = 20 * SCALE, 20 * SCALE
    HEADER_H, BASE_ROW_H = 80 * SCALE, 80 * SCALE
    FRAME, PAD_X, PAD_TOP, PAD_BOT, TITLE_H = (
        2 * SCALE,
        28 * SCALE,
        24 * SCALE,
        24 * SCALE,
        64 * SCALE,
    )

    BG, HEADER_BG, HEADER_TEXT = "#FFFFFF", "#1A3A5C", "#FFFFFF"
    TEXT_COLOR, GRID_COLOR, TITLE_COLOR, FRAME_COLOR = "#000000", "#000000", "#1A2B3C", "#F0F2F5"

    font = ImageFont.truetype(_FONT_BOLD_PATH, FONT_SIZE)
    title_font = ImageFont.truetype(_FONT_BOLD_PATH, TITLE_SIZE)
    char_w = int(font.getlength("M"))

    headers = [
        "Incident ID",
        "Site Name",
        "Site Code",
        "Occurred At",
        "Outage",
        "INC-WO ID",
        "INC-WO Status",
        "Last Comment",
    ]
    col_w_chars = [16, 18, 10, 16, 7, 20, 16, 44]
    col_w_px = [chars * char_w + CELL_PAD_X * 2 for chars in col_w_chars]
    table_w = sum(col_w_px)

    data_rows, row_heights = [], []
    for row in rows:
        comment = (row.get("last_comments") or "").replace("\n", " ").strip()
        comment_lines = _wrap_text_px(comment, font, col_w_px[7] - CELL_PAD_X * 2)[:5]
        data_rows.append(
            [
                str(row.get("incident_id") or ""),
                str(row.get("site_name") or "—"),
                str(row.get("site_code") or "—"),
                (row.get("occurred_at") or "")[:16],
                _format_outage(row["outage_min"]),
                str(row.get("wo_id") or "—"),
                str(row.get("wo_status") or "—"),
                comment_lines,
            ]
        )
        row_heights.append(
            max(
                BASE_ROW_H,
                CELL_PAD_Y * 2
                + len(comment_lines) * FONT_SIZE
                + (len(comment_lines) - 1) * (6 * SCALE),
            )
        )

    img_w = table_w + (PAD_X + FRAME) * 2
    img_h = FRAME * 2 + PAD_TOP + TITLE_H + HEADER_H + sum(row_heights) + PAD_BOT
    img = Image.new("RGB", (img_w, img_h), FRAME_COLOR)
    draw = ImageDraw.Draw(img)
    draw.rectangle([FRAME, FRAME, img_w - FRAME - 1, img_h - FRAME - 1], fill=BG)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    title_y = FRAME + PAD_TOP + (TITLE_H - TITLE_SIZE) // 2
    draw.text((FRAME + PAD_X, title_y), f"{title}  —  {now_str}", fill=TITLE_COLOR, font=title_font)

    tx, ty = FRAME + PAD_X, FRAME + PAD_TOP + TITLE_H
    table_h = HEADER_H + sum(row_heights)
    draw.rectangle([tx, ty, tx + table_w, ty + table_h], fill=BG)
    draw.rectangle([tx, ty, tx + table_w, ty + HEADER_H], fill=HEADER_BG)

    cx = tx
    for i, header in enumerate(headers):
        col_w = col_w_px[i]
        h_w = int(font.getlength(header))
        draw.text(
            (cx + max(CELL_PAD_X, (col_w - h_w) // 2), ty + (HEADER_H - FONT_SIZE) // 2),
            header,
            fill=HEADER_TEXT,
            font=font,
        )
        cx += col_w

    cy = ty + HEADER_H
    for ri, values in enumerate(data_rows):
        row_h = row_heights[ri]
        cx = tx
        for ci in range(7):
            col_w = col_w_px[ci]
            value = values[ci]
            if ci == 4:  # Outage — right-align
                v_w = int(font.getlength(value))
                x = cx + col_w - CELL_PAD_X - v_w
            else:
                x = cx + CELL_PAD_X
            draw.text((x, cy + (row_h - FONT_SIZE) // 2), value, fill=TEXT_COLOR, font=font)
            cx += col_w
        for li, line in enumerate(values[7]):
            draw.text(
                (cx + CELL_PAD_X, cy + CELL_PAD_Y + li * (FONT_SIZE + 4 * SCALE)),
                line,
                fill=TEXT_COLOR,
                font=font,
            )
        cy += row_h

    cy = ty + HEADER_H
    for row_h in row_heights:
        draw.line([tx, cy, tx + table_w, cy], fill=GRID_COLOR, width=SCALE)
        cy += row_h
    cx = tx
    for col_w in col_w_px[:-1]:
        cx += col_w
        draw.line([cx, ty, cx, ty + table_h], fill=GRID_COLOR, width=SCALE)
    draw.rectangle([tx, ty, tx + table_w, ty + table_h], outline=GRID_COLOR, width=SCALE)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.getvalue()


def _is_l2_support(row):
    """True only for an L2 Support Level (e.g. "L2 On-Site") — used by the
    three INC-WO Telegram alerts (Site Down, Category Power, General) to
    send L2 rows only. Anything else (L3, blank, or any other value) is
    excluded — these alerts are for the L2 On-Site team specifically."""
    return (row.get("support_level") or "").strip().upper().startswith("L2")


def _error_detail(e):
    """`str(e)` on a requests HTTPError is just the status line (e.g. "400
    Client Error: Bad Request for url: ...") — Telegram's own reason (e.g.
    "Bad Request: chat not found", "Forbidden: bot was kicked from the
    group chat") is in the response body instead. Falls back to str(e) for
    any other exception (timeouts, connection errors) that has no body."""
    resp = getattr(e, "response", None)
    if resp is not None:
        try:
            return resp.json().get("description", resp.text)
        except ValueError:
            return resp.text
    return str(e)


def _argb(hex_color):
    """"#1A3A5C" -> "FF1A3A5C" — openpyxl colors want an 8-digit ARGB
    string; every color used in this codebase is a plain 6-digit RGB hex
    (the PNG tables' own color constants), so this just adds full opacity."""
    h = hex_color.lstrip("#")
    return f"FF{h}" if len(h) == 6 else h


# Same incident/inc_wo record links the dashboard's own drilldown pages
# build (see incwo.html's <a href="https://prd-web-mc.cellcard.com.kh/...">)
# — every INC-WO cache table these alerts read from already carries
# incident_numeric_id/wo_numeric_id (see app/database/cache.py), so no new
# data is needed to link Excel cells the same way.
_INCIDENT_FORM_URL = "https://prd-web-mc.cellcard.com.kh/incident/form/{id}"
_INC_WO_FORM_URL = "https://prd-web-mc.cellcard.com.kh/inc_wo/form/{id}"
_EXCEL_LINK_ARGB = "FF0563C1"  # Excel's own default hyperlink blue


def _incident_link(row):
    numeric_id = row.get("incident_numeric_id")
    return _INCIDENT_FORM_URL.format(id=numeric_id) if numeric_id else None


def _inc_wo_link(row):
    numeric_id = row.get("wo_numeric_id")
    return _INC_WO_FORM_URL.format(id=numeric_id) if numeric_id else None


def _build_excel_bytes(
    columns,
    rows,
    title,
    status_key=None,
    status_colors=None,
    priority_fn=None,
    hyperlinks=None,
    left_align=None,
):
    """Builds a styled .xlsx workbook of `rows` — dark-navy header banner
    matching the PNG tables' own look, a frozen header row, autofilter,
    autosized columns, and light banded rows for readability.

    `columns` is a sequence of (header, extractor) pairs, where extractor
    is either a row dict key or a callable(row) -> value; a missing/blank
    value renders as "—", same convention the PNG tables use. Pass
    `status_key`/`status_colors` to color one column's text the same way
    the PNG table does (e.g. INC-WO Status); pass `priority_fn(row)` to
    shade a whole row the same pink the PNG table uses for hub/Gold/Diamond
    sites. Pass `hyperlinks` as a {header: fn(row) -> url_or_None} map to
    make that column's cells clickable (styled Excel-hyperlink-blue, no
    underline — per explicit request) — a row with no numeric id (fn
    returns None/falsy) stays plain text, same conditional-link behavior
    incwo.html itself uses. Every data cell is centered by default — pass
    `left_align` as a set/list of header strings (e.g. free-typed prose
    columns like Fault Description) to left-align just those columns
    instead, per explicit request.

    Returns bytes, or None if openpyxl isn't installed — caller decides
    whether to skip the attachment silently, same convention as
    _render_table_image()'s own Pillow guard."""
    if not _HAS_OPENPYXL:
        return None

    wb = Workbook()
    ws = wb.active
    ws.title = "Alert"

    # Solid black, not hairline-thin — a light-grey grid disappears at
    # normal zoom; black keeps every cell boundary visible without opening
    # the file and zooming in.
    thick = Side(style="medium", color=_EXCEL_BORDER_ARGB)
    border = Border(left=thick, right=thick, top=thick, bottom=thick)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(columns), 1))
    title_cell = ws.cell(row=1, column=1, value=f"{title}  —  {now_str}")
    title_cell.font = Font(bold=True, size=_EXCEL_TITLE_FONT_SIZE, color="FF1A2B3C")
    ws.row_dimensions[1].height = 28

    header_row = 2
    for ci, (header, _extractor) in enumerate(columns, start=1):
        cell = ws.cell(row=header_row, column=ci, value=header)
        cell.font = Font(bold=True, size=_EXCEL_HEADER_FONT_SIZE, color="FFFFFFFF")
        cell.fill = PatternFill("solid", fgColor=_EXCEL_HEADER_ARGB)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border
    ws.row_dimensions[header_row].height = 26

    max_len = [len(header) for header, _ in columns]
    for ri, row in enumerate(rows, start=header_row + 1):
        is_priority = bool(priority_fn(row)) if priority_fn else False
        band = (not is_priority) and (ri - header_row) % 2 == 0
        for ci, (header, extractor) in enumerate(columns, start=1):
            value = extractor(row) if callable(extractor) else (row.get(extractor) or "—")
            is_status = status_key and header == status_key and status_colors and value in status_colors
            link_url = hyperlinks[header](row) if hyperlinks and header in hyperlinks else None
            horizontal = "left" if left_align and header in left_align else "center"
            cell = ws.cell(row=ri, column=ci, value=value)
            cell.border = border
            cell.alignment = Alignment(horizontal=horizontal, vertical="center")
            if link_url:
                cell.hyperlink = link_url
                cell.font = Font(size=_EXCEL_DATA_FONT_SIZE, color=_EXCEL_LINK_ARGB)
            else:
                cell.font = Font(
                    size=_EXCEL_DATA_FONT_SIZE,
                    bold=bool(is_status),
                    color=_argb(status_colors[value]) if is_status else "FF000000",
                )
            if is_priority:
                cell.fill = PatternFill("solid", fgColor=_EXCEL_PRIORITY_ARGB)
            elif band:
                cell.fill = PatternFill("solid", fgColor=_EXCEL_ALT_ROW_ARGB)
            max_len[ci - 1] = max(max_len[ci - 1], len(str(value)))
        ws.row_dimensions[ri].height = _EXCEL_DATA_ROW_HEIGHT

    for ci, length in enumerate(max_len, start=1):
        ws.column_dimensions[get_column_letter(ci)].width = min(max(length + 4, 12), 60)

    ws.freeze_panes = f"A{header_row + 1}"
    if rows:
        ws.auto_filter.ref = f"A{header_row}:{get_column_letter(len(columns))}{header_row}"

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def _send_telegram_excel(token, chat_ids, excel_bytes, filename):
    """Sends the Excel attachment via the same sendDocument endpoint as the
    PNG table image — shared by all 4 Telegram alerts so "also send this
    alert's rows as .xlsx" behaves identically everywhere."""
    url = _TELEGRAM_SEND_DOCUMENT_URL.format(token=token)
    sent = True
    for chat_id in chat_ids:
        try:
            files = {"document": (filename, excel_bytes, _EXCEL_MIME)}
            resp = requests.post(url, files=files, data={"chat_id": chat_id}, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Telegram Excel send failed for chat {chat_id}: {_error_detail(e)}")
            sent = False
    return sent


def _send_telegram_photo(token, chat_ids, photo_bytes):
    """Sends as a document (not sendPhoto) — Telegram recompresses photos,
    which blurs small table text; documents are delivered untouched."""
    url = _TELEGRAM_SEND_DOCUMENT_URL.format(token=token)
    sent = True
    for chat_id in chat_ids:
        try:
            files = {"document": ("site-down-alert.png", photo_bytes, "image/png")}
            resp = requests.post(url, files=files, data={"chat_id": chat_id}, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Telegram image send failed for chat {chat_id}: {_error_detail(e)}")
            sent = False
    return sent


def _send_telegram_text(token, chat_ids, text):
    url = _TELEGRAM_SEND_MESSAGE_URL.format(token=token)
    sent = True
    for chat_id in chat_ids:
        try:
            resp = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Telegram text send failed for chat {chat_id}: {_error_detail(e)}")
            sent = False
    return sent


# (header, extractor) pairs for the Excel attachment — mirrors
# _render_table_image()'s own `headers`/row-building, minus the pixel-width
# truncation (Excel autosizes columns instead of wrapping/clipping text).
_EXCEL_COLUMNS = (
    ("Incident ID", lambda r: r.get("incident_id") or "—"),
    ("Site Name", lambda r: r.get("site_name") or "—"),
    ("Site Code", lambda r: r.get("site_code") or "—"),
    ("Occurred At", lambda r: (r.get("occurred_at") or "")[:16]),
    ("Outage", lambda r: _format_outage(r["outage_min"])),
    ("INC-WO ID", lambda r: r.get("wo_id") or "—"),
    ("INC-WO Status", lambda r: r.get("wo_status") or "—"),
    ("Last Comment", lambda r: (r.get("last_comments") or "").replace("\n", " ").strip()),
)


def send_site_down_alert(
    threshold_min=None, incident_site_down_cache_repository=None, cache_repository=None
):
    """Send one Telegram alert listing every Incident Site Down whose
    outage has passed `threshold_min` (defaults to
    app.config['ALERT_THRESHOLD_MIN']) — as a table image, or plain text if
    Pillow/the font isn't available. Returns {'sent': bool, 'count': int}.
    Raises EnvironmentError if TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_IDS aren't
    configured — callers decide whether that's fatal or just a skip.
    """
    token = current_app.config["TELEGRAM_BOT_TOKEN"]
    chat_ids = _chat_ids(current_app.config["TELEGRAM_CHAT_IDS"])
    if not token or not chat_ids:
        raise EnvironmentError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_IDS must be set in .env")

    if threshold_min is None:
        threshold_min = current_app.config["ALERT_THRESHOLD_MIN"]

    rows = _site_down_over_threshold(
        threshold_min, incident_site_down_cache_repository, cache_repository
    )
    if not rows:
        logger.info(f"No Incident Site Down over {threshold_min} minutes — nothing to send")
        return {"sent": False, "count": 0}

    photo = _render_table_image(rows, "Site Down Alerts")
    if photo:
        sent = _send_telegram_photo(token, chat_ids, photo)
    else:
        sent = _send_telegram_text(token, chat_ids, _format_message(rows, threshold_min))

    excel = _build_excel_bytes(
        _EXCEL_COLUMNS,
        rows,
        "Site Down Alerts",
        hyperlinks={"Incident ID": _incident_link, "INC-WO ID": _inc_wo_link},
    )
    if excel:
        sent = _send_telegram_excel(token, chat_ids, excel, "site-down-alert.xlsx") and sent

    logger.info(
        f"Sent Telegram Site Down alert — {len(rows)} incident(s) to {len(chat_ids)} chat(s)"
    )
    return {"sent": sent, "count": len(rows)}


def _work():
    try:
        send_site_down_alert()
    except EnvironmentError as e:
        logger.error(f"Telegram alert not configured: {e}")
    except Exception as e:
        logger.error(f"Telegram alert failed: {e}")


def start(app, interval_seconds=None):
    """Start the background alert loop, once per process. See
    scheduler_utils.py for the shared loop/guard logic; the computed
    `first_run_delay` is what makes the first send land on a clean clock
    boundary instead of immediately on startup (see module docstring
    above). `next_delay_fn` re-derives that same aligned delay before every
    subsequent sleep too — otherwise each run's own duration (Telegram
    network calls, image rendering) would push every following send a bit
    later, compounding into steady drift off the clock boundary cycle after
    cycle."""
    wait = interval_seconds or app.config["ALERT_INTERVAL_SECONDS"]
    tz_name = app.config["TIMEZONE"]
    delay = seconds_until_next_aligned_time(wait, tz_name)
    start_singleton_loop(
        app,
        _work,
        wait,
        thread_name="telegram-site-down-alert",
        log_message=f"Telegram Site Down alert scheduler started (every {wait}s, "
        f"first run in {delay:.0f}s)",
        first_run_delay=delay,
        next_delay_fn=lambda: seconds_until_next_aligned_time(wait, tz_name),
    )
