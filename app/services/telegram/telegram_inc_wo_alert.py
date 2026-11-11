"""Sends a Telegram alert listing every INC-WO Site Down row currently
open (INC_WO_ALERT_THRESHOLD_MIN defaults to 0 — every row), rendered as
a table image, same approach as telegram_alert.py. Unlike that alert's
threshold-based nudge, this reads as "the current list right now",
refreshed every INC_WO_ALERT_INTERVAL_SECONDS (default 900s).

Reads the already-synced inc_wo_site_down cache. Every row read is
mirrored into its own telegram_inc_wo_alert_cache table before the
threshold filter runs. Also attaches the same rows as a styled .xlsx.

Sent via a separate bot/chat (TELEGRAM_BOT_INC_WO_TOKEN/
TELEGRAM_CHAT_IDS_INC_WO) — the bot must already be a member of that
chat or Telegram returns "chat not found".

start() runs clock-aligned like telegram_alert.py's own loop — all
offsets 0, landing at the same instant as every other Telegram alert,
per explicit request (not staggered).
"""

import io
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from flask import current_app

from app.repositories.incwo.incwo_status_cache_repository import IncWoStatusCacheRepository
from app.repositories.telegram.telegram_inc_wo_alert_cache_repository import (
    TelegramIncWoAlertCacheRepository,
)
from app.services.scheduler_utils import seconds_until_next_aligned_time, start_singleton_loop
from app.services.telegram.telegram_alert import (
    _FONT_DIR,
    _TELEGRAM_SEND_DOCUMENT_URL,
    _build_excel_bytes,
    _chat_ids,
    _error_detail,
    _format_outage,
    _inc_wo_link,
    _incident_link,
    _is_l2_support,
    _send_telegram_excel,
    _send_telegram_text,
)
from app.utils.datetime import elapsed_minutes
from app.utils.logger import get_logger

try:
    from PIL import Image, ImageDraw, ImageFont

    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

# Shared INC-WO renderer uses Huawei Sans Bold throughout.
_FONT_PATH = os.path.join(_FONT_DIR, "HuaweiSans-Bold.ttf")
_TITLE_FONT_PATH = os.path.join(_FONT_DIR, "HuaweiSans-Bold.ttf")

logger = get_logger(__name__)

_SITE_DOWN_TABLE = "inc_wo_site_down"
_CACHE_TABLE = "telegram_inc_wo_alert_cache"

# 0 — lands on the interval boundary, same as every other Telegram
# alert. All read local cache only (no live DB query), so firing
# together isn't a collision risk — deliberately not staggered.
_OFFSET_SECONDS = 0


def _cache_telegram_rows(rows, cache_repository=None):
    """Mirror every fetched row into telegram_inc_wo_alert_cache.
    Best-effort — a cache write failure shouldn't stop the alert."""
    cache_repository = cache_repository or TelegramIncWoAlertCacheRepository()
    try:
        cache_repository.replace_all(_CACHE_TABLE, rows)
    except Exception as e:
        logger.error(f"telegram_inc_wo_alert_cache write failed: {e}")


def _inc_wo_site_down_over_threshold(
    threshold_min, status_cache_repository=None, cache_repository=None
):
    """Every INC-WO Site Down row whose outage_min — minutes since the
    WO was created, not the incident — has passed `threshold_min`,
    longest-open first.

    Rows with no wo_id yet, or whose Support Level isn't L2 (this alert
    is for the L2 On-Site team only), are excluded from what gets sent,
    but still mirrored into the raw cache as an audit trail."""
    status_cache_repository = status_cache_repository or IncWoStatusCacheRepository()
    rows = status_cache_repository.fetch_all(_SITE_DOWN_TABLE)
    for row in rows:
        row["outage_min"] = elapsed_minutes(row.get("wo_created_at"))
    _cache_telegram_rows(rows, cache_repository)

    over_threshold = [
        row
        for row in rows
        if row.get("wo_id")
        and row["outage_min"] >= threshold_min
        and _is_l2_support(row)
    ]
    over_threshold.sort(key=lambda row: row["outage_min"], reverse=True)
    return over_threshold


def _format_message(rows, threshold_min):
    """Plain-text fallback, used only if Pillow/the font can't render an
    image (e.g. a stripped-down deploy without Pillow installed)."""
    hours = threshold_min // 60
    lines = [f"INC-WO Site Down — open over {hours}h ({len(rows)})", ""]
    for row in rows:
        site = row.get("site_name") or row.get("site_code") or "Unknown site"
        lines.append(
            f"• {row.get('wo_id') or row.get('incident_id')} — {site} "
            f"— {_format_outage(row['outage_min'])} — {row.get('province') or 'Unknown province'}"
        )
    return "\n".join(lines)


# (header, char width, row key) — one entry per column, matching the
# dashboard's own INC-WO Site Down drilldown/CSV column order, one row
# per record. "Fault Description" truncates with "..." (see
# _truncate_text_px()) rather than wrapping, so every row is uniform height.
_COLUMNS = (
    ("Incident ID", 14, "incident_id"),
    ("INC-WO ID", 15, "wo_id"),
    ("INC-WO Created At", 16, "wo_created_at"),
    ("INC-WO Status", 14, "wo_status"),
    ("Site Name", 14, "site_name"),
    ("Site Code", 8, "site_code"),
    ("Overdue", 5, "overdue"),
    ("Support Level", 12, "support_level"),
    ("Fault Description", 24, "fault_description"),
    ("NMS", 8, "nms"),
    ("Hub Site", 12, "hub_site"),
    ("Site Grade", 10, "site_grade"),
    ("Province", 14, "province"),
)
_STATUS_COLUMN_INDEX = 3  # "INC-WO Status" — the only color-coded column

# (header, extractor) pairs for the Excel attachment — same columns as
# _COLUMNS, minus the pixel-width truncation (Excel autosizes columns).
# Shared by all 3 alerts that use _render_inc_wo_table_image.
_EXCEL_SPECIAL_EXTRACTORS = {
    "wo_created_at": lambda r: (r.get("wo_created_at") or "")[:16],
    "site_name": lambda r: (
        "—" if (r.get("site_name") or "").startswith("Other Site") else (r.get("site_name") or "—")
    ),
    "fault_description": lambda r: (r.get("fault_description") or "—").replace("\n", " ").strip(),
}
_EXCEL_COLUMNS = tuple(
    (header, _EXCEL_SPECIAL_EXTRACTORS.get(key, key)) for header, _chars, key in _COLUMNS
)

# Free-typed prose/long values — left-aligned rather than centered.
# Shared by all 3 alerts that use _EXCEL_COLUMNS.
_EXCEL_LEFT_ALIGN_HEADERS = {"Fault Description", "Hub Site", "Province", "Site Name"}


def _truncate_text_px(text, font, max_px):
    """Cuts `text` to fit `max_px` width, appending "..." if anything
    was cut — character by character, not word by word."""
    if not text or font.getlength(text) <= max_px:
        return text
    ellipsis_w = font.getlength("...")
    truncated = ""
    for ch in text:
        if font.getlength(truncated + ch) + ellipsis_w > max_px:
            break
        truncated += ch
    return truncated.rstrip() + "..."


# Same colors as the dashboard's own status badge, so statuses read the
# same here as on screen. Falls back to plain black for any unmapped status.
_STATUS_COLORS = {
    "New": "#0487e2",
    "Assigned": "#94a3b8",
    "Acknowledged": "#8b5cf6",
    "In Progress": "#f59e0b",
    "On Hold": "#ea580c",
    "Resolved": "#10b981",
    "Reopened": "#ef4444",
    "Returned": "#ec4899",
}

# A site is "priority" for highlighting if it's any kind of hub, or its
# grade is Gold/Diamond — either alone qualifies.
_TOP_SITE_GRADES = {"Gold", "Diamond"}
_PRIORITY_ROW_BG = "#FFCDD2"


def _is_priority_site(row):
    hub = (row.get("hub_site") or "").strip()
    return hub not in ("", "Not Hub") or row.get("site_grade") in _TOP_SITE_GRADES


def _render_inc_wo_table_image(rows, title):
    """Renders the INC-WO table (per _COLUMNS) as a PNG — shared by both
    the Site Down and Category Power alerts. INC-WO Status is colored per
    _STATUS_COLORS; a Hub/Gold/Diamond row is shaded _PRIORITY_ROW_BG.
    Returns None if Pillow/the font isn't available."""
    if not _HAS_PIL or not os.path.exists(_FONT_PATH) or not os.path.exists(_TITLE_FONT_PATH):
        return None

    # SCALE=1, not telegram_alert.py's 2 — this table has 15 columns, and
    # at SCALE=2 the file got large enough that Telegram's thumbnail
    # generator squashed the preview into an unreadable blur (the full
    # image opens sharp either way; this only affects the thumbnail/size).
    SCALE = 1
    FONT_SIZE, TITLE_SIZE = 56 * SCALE, 62 * SCALE
    CELL_PAD_X = 26 * SCALE
    HEADER_H, BASE_ROW_H = 138 * SCALE, 138 * SCALE
    FRAME, PAD_X, PAD_TOP, PAD_BOT, TITLE_H = (
        2 * SCALE,
        28 * SCALE,
        24 * SCALE,
        24 * SCALE,
        100 * SCALE,
    )

    BG, HEADER_BG, HEADER_TEXT = "#FFFFFF", "#1A3A5C", "#FFFFFF"
    TEXT_COLOR, GRID_COLOR, TITLE_COLOR, FRAME_COLOR = "#000000", "#000000", "#000000", "#F0F2F5"

    font = ImageFont.truetype(_FONT_PATH, FONT_SIZE)
    title_font = ImageFont.truetype(_TITLE_FONT_PATH, TITLE_SIZE)
    char_w = int(font.getlength("M"))

    headers = [c[0] for c in _COLUMNS]
    col_w_px = [chars * char_w + CELL_PAD_X * 2 for _, chars, _ in _COLUMNS]
    table_w = sum(col_w_px)

    data_rows = []
    row_priority = []
    for row in rows:
        row_priority.append(_is_priority_site(row))
        values = []
        for ci, (_header, _chars, key) in enumerate(_COLUMNS):
            if key == "wo_created_at":
                values.append((row.get(key) or "")[:16])
                continue
            if key == "site_name":
                # "Other Site (CODE)" overflowed into the next column —
                # Site Code has its own column, so leave this blank instead.
                text = row.get(key) or "—"
                if text.startswith("Other Site"):
                    text = "—"
            elif key == "fault_description":
                text = (row.get(key) or "—").replace("\n", " ").strip()
            else:
                text = str(row.get(key) or "—")
            values.append(_truncate_text_px(text, font, col_w_px[ci] - CELL_PAD_X * 2))
        data_rows.append(values)

    img_w = table_w + (PAD_X + FRAME) * 2
    img_h = FRAME * 2 + PAD_TOP + TITLE_H + HEADER_H + len(data_rows) * BASE_ROW_H + PAD_BOT
    img = Image.new("RGB", (img_w, img_h), FRAME_COLOR)
    draw = ImageDraw.Draw(img)
    draw.rectangle([FRAME, FRAME, img_w - FRAME - 1, img_h - FRAME - 1], fill=BG)

    now_str = datetime.now(ZoneInfo(current_app.config["TIMEZONE"])).strftime("%Y-%m-%d %H:%M")
    title_y = FRAME + PAD_TOP + (TITLE_H - TITLE_SIZE) // 2
    draw.text((FRAME + PAD_X, title_y), f"{title}  —  {now_str}", fill=TITLE_COLOR, font=title_font)

    tx, ty = FRAME + PAD_X, FRAME + PAD_TOP + TITLE_H
    table_h = HEADER_H + len(data_rows) * BASE_ROW_H
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
    for values, is_priority in zip(data_rows, row_priority):
        if is_priority:
            draw.rectangle([tx, cy, tx + table_w, cy + BASE_ROW_H], fill=_PRIORITY_ROW_BG)
        cx = tx
        for ci, col_w in enumerate(col_w_px):
            color = TEXT_COLOR
            if ci == _STATUS_COLUMN_INDEX:
                color = _STATUS_COLORS.get(values[ci], TEXT_COLOR)
            draw.text(
                (cx + CELL_PAD_X, cy + (BASE_ROW_H - FONT_SIZE) // 2),
                values[ci],
                fill=color,
                font=font,
            )
            cx += col_w
        cy += BASE_ROW_H

    cy = ty + HEADER_H
    for _ in range(len(data_rows)):
        draw.line([tx, cy, tx + table_w, cy], fill=GRID_COLOR, width=SCALE)
        cy += BASE_ROW_H
    cx = tx
    for col_w in col_w_px[:-1]:
        cx += col_w
        draw.line([cx, ty, cx, ty + table_h], fill=GRID_COLOR, width=SCALE)
    draw.rectangle([tx, ty, tx + table_w, ty + table_h], outline=GRID_COLOR, width=SCALE)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.getvalue()


def _send_telegram_document(token, chat_ids, photo_bytes):
    """Sends as a document, not sendPhoto (avoids Telegram's photo
    recompression blurring small table text) — its own filename so this
    alert's file isn't indistinguishable from telegram_alert.py's."""
    url = _TELEGRAM_SEND_DOCUMENT_URL.format(token=token)
    sent = True
    for chat_id in chat_ids:
        try:
            files = {"document": ("inc-wo-site-down-alert.png", photo_bytes, "image/png")}
            resp = requests.post(url, files=files, data={"chat_id": chat_id}, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Telegram image send failed for chat {chat_id}: {_error_detail(e)}")
            sent = False
    return sent


def send_inc_wo_site_down_alert(
    threshold_min=None, status_cache_repository=None, cache_repository=None
):
    """Send one Telegram alert listing every INC-WO Site Down whose WO has
    been open past `threshold_min` (defaults to
    app.config['INC_WO_ALERT_THRESHOLD_MIN']) — as a table image, or plain
    text if Pillow/the font isn't available. Returns {'sent': bool,
    'count': int}. Raises EnvironmentError if
    TELEGRAM_BOT_INC_WO_TOKEN/TELEGRAM_CHAT_IDS_INC_WO aren't configured —
    callers decide whether that's fatal or just a skip."""
    token = current_app.config["TELEGRAM_BOT_INC_WO_TOKEN"]
    chat_ids = _chat_ids(current_app.config["TELEGRAM_CHAT_IDS_INC_WO"])
    if not token or not chat_ids:
        raise EnvironmentError(
            "TELEGRAM_BOT_INC_WO_TOKEN and TELEGRAM_CHAT_IDS_INC_WO must be set in .env"
        )

    if threshold_min is None:
        threshold_min = current_app.config["INC_WO_ALERT_THRESHOLD_MIN"]

    rows = _inc_wo_site_down_over_threshold(
        threshold_min, status_cache_repository, cache_repository
    )
    if not rows:
        logger.info(f"No INC-WO Site Down over {threshold_min} minutes — nothing to send")
        return {"sent": False, "count": 0}

    photo = _render_inc_wo_table_image(rows, "INC-WO Site Down Alerts")
    if photo:
        sent = _send_telegram_document(token, chat_ids, photo)
    else:
        sent = _send_telegram_text(token, chat_ids, _format_message(rows, threshold_min))

    excel = _build_excel_bytes(
        _EXCEL_COLUMNS,
        rows,
        "INC-WO Site Down Alerts",
        status_key="INC-WO Status",
        status_colors=_STATUS_COLORS,
        priority_fn=_is_priority_site,
        hyperlinks={"Incident ID": _incident_link, "INC-WO ID": _inc_wo_link},
        left_align=_EXCEL_LEFT_ALIGN_HEADERS,
    )
    if excel:
        sent = _send_telegram_excel(token, chat_ids, excel, "inc-wo-site-down-alert.xlsx") and sent

    # `sent` tracks every underlying send call's own success (image/text AND
    # excel) — logging "Sent" unconditionally here, regardless of that
    # value, previously made a fully-failed send (e.g. "chat not found")
    # look identical to a real success in the logs.
    if sent:
        logger.info(
            f"Sent Telegram INC-WO Site Down alert — {len(rows)} row(s) to {len(chat_ids)} chat(s)"
        )
    else:
        logger.error(
            f"Telegram INC-WO Site Down alert FAILED to send — {len(rows)} row(s), "
            f"{len(chat_ids)} chat(s) (see the send error(s) logged above)"
        )
    return {"sent": sent, "count": len(rows)}


def _work():
    try:
        send_inc_wo_site_down_alert()
    except EnvironmentError as e:
        logger.error(f"Telegram INC-WO alert not configured: {e}")
    except Exception as e:
        logger.error(f"Telegram INC-WO alert failed: {e}")


def start(app, interval_seconds=None):
    """Start the background alert loop, once per process — same
    first_run_delay/next_delay_fn pattern as telegram_alert.py's start(),
    offset by _OFFSET_SECONDS."""
    wait = interval_seconds or app.config["INC_WO_ALERT_INTERVAL_SECONDS"]
    tz_name = app.config["TIMEZONE"]
    delay = seconds_until_next_aligned_time(wait, tz_name, offset_seconds=_OFFSET_SECONDS)
    start_singleton_loop(
        app,
        _work,
        wait,
        thread_name="telegram-inc-wo-site-down-alert",
        log_message=f"Telegram INC-WO Site Down alert scheduler started (every {wait}s, "
        f"first run in {delay:.0f}s)",
        first_run_delay=delay,
        next_delay_fn=lambda: seconds_until_next_aligned_time(
            wait, tz_name, offset_seconds=_OFFSET_SECONDS
        ),
    )
