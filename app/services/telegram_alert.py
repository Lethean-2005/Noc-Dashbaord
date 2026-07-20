"""Sends a Telegram alert listing every Incident Site Down whose outage has
passed ALERT_THRESHOLD_MIN (default 240 minutes / 4 hours), rendered as a
table image (via Pillow) rather than a plain text message — sent as a
document so Telegram doesn't recompress it and blur the text.

Queries Postgres directly (app/database/queries/site_down.sql, shared with
the "Incident Site Down" dashboard card's cache sync), not the
incident_by_status cache — that cache is deliberately scoped to
status IN ('new', 'in_progress') for the dashboard badges, but this alert's
real definition (per the source system's own Incident filter) is broader:
Incident Category = Site Down, Status is not Closed, Cleared Alarm Received
is FALSE. A live query is fine here since this only runs once every few
hours, never on a page load. Never runs unless TELEGRAM_BOT_TOKEN/
TELEGRAM_CHAT_IDS are set in .env.

start() runs this on a background loop, once every ALERT_INTERVAL_SECONDS
(default 14400s / 4 hours) — called once from app/__init__.py::create_app().
The first send happens after the first full interval, not immediately on
startup, so restarting the dev server (which happens often) can't spam the
Telegram chat with a repeat alert.
"""
import io
import os
from datetime import datetime

import requests
from flask import current_app

from app.repositories.incident_repository import IncidentRepository
from app.services.scheduler_utils import start_singleton_loop
from app.utils.datetime import elapsed_minutes
from app.utils.logger import get_logger

try:
    from PIL import Image, ImageDraw, ImageFont
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

logger = get_logger(__name__)

_TELEGRAM_SEND_MESSAGE_URL = "https://api.telegram.org/bot{token}/sendMessage"
_TELEGRAM_SEND_DOCUMENT_URL = "https://api.telegram.org/bot{token}/sendDocument"

# app/static/fonts/ (see base.html) — same Exo 2 family used across the
# dashboard's own UI, so the alert image looks consistent with the app.
_FONT_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "fonts")
_FONT_BOLD_PATH = os.path.join(_FONT_DIR, "Exo2-Bold.ttf")


def _chat_ids(raw):
    """'-100123, -100456,' -> ['-100123', '-100456'] — tolerates blank
    entries from a trailing comma or extra whitespace."""
    return [chat_id.strip() for chat_id in raw.split(",") if chat_id.strip()]


def _normalize_row(row):
    """Maps site_down.sql's quoted, mixed-case column aliases onto clean
    snake_case keys used by the rest of this module."""
    return {
        "incident_id": row.get("Incident ID") or "",
        "incident_status": row.get("Incident Status") or "",
        "wo_id": row.get("INC-WO ID") or "",
        "wo_created_at": str(row.get("INC-WO Created At") or ""),
        "wo_status": row.get("INC-WO Status") or "",
        "site_name": row.get("Site Name") or "",
        "site_code": row.get("Site Code") or "",
        "occurred_at": str(row.get("Occurred At") or ""),
        "l1_noc_investigation_result": row.get("L1 NOC Investigation Result") or "",
        "nms": row.get("NMS") or "",
        "hub_site": row.get("Hub Site") or "",
        "site_grade": row.get("Site Grade") or "",
        "province": row.get("Province") or "",
        "district": row.get("District") or "",
        "commune": row.get("Commune") or "",
    }


def _site_down_over_threshold(threshold_min, incident_repository=None):
    """Every Site Down incident not yet Closed whose alarm hasn't cleared
    (per site_down.sql) and whose outage has passed `threshold_min` minutes,
    longest-outage first."""
    incident_repository = incident_repository or IncidentRepository()
    rows = [_normalize_row(r) for r in incident_repository.fetch_site_down()]
    over_threshold = []
    for row in rows:
        outage_min = elapsed_minutes(row.get("occurred_at"))
        if outage_min >= threshold_min:
            row["outage_min"] = outage_min
            over_threshold.append(row)
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
    FRAME, PAD_X, PAD_TOP, PAD_BOT, TITLE_H = 2 * SCALE, 28 * SCALE, 24 * SCALE, 24 * SCALE, 64 * SCALE

    BG, HEADER_BG, HEADER_TEXT = "#FFFFFF", "#1A3A5C", "#FFFFFF"
    TEXT_COLOR, GRID_COLOR, TITLE_COLOR, FRAME_COLOR = "#000000", "#000000", "#1A2B3C", "#F0F2F5"

    font = ImageFont.truetype(_FONT_BOLD_PATH, FONT_SIZE)
    title_font = ImageFont.truetype(_FONT_BOLD_PATH, TITLE_SIZE)
    char_w = int(font.getlength("M"))

    headers = ["Incident ID", "Site Name", "Site Code", "Occurred At",
               "Outage", "INC-WO ID", "INC-WO Status", "Last Comment"]
    col_w_chars = [16, 18, 10, 16, 7, 20, 16, 44]
    col_w_px = [chars * char_w + CELL_PAD_X * 2 for chars in col_w_chars]
    table_w = sum(col_w_px)

    data_rows, row_heights = [], []
    for row in rows:
        comment = (row.get("l1_noc_investigation_result") or "").replace("\n", " ").strip()
        comment_lines = _wrap_text_px(comment, font, col_w_px[7] - CELL_PAD_X * 2)[:5]
        data_rows.append([
            str(row.get("incident_id") or ""),
            str(row.get("site_name") or "—"),
            str(row.get("site_code") or "—"),
            (row.get("occurred_at") or "")[:16],
            _format_outage(row["outage_min"]),
            str(row.get("wo_id") or "—"),
            str(row.get("wo_status") or "—"),
            comment_lines,
        ])
        row_heights.append(max(BASE_ROW_H, CELL_PAD_Y * 2 + len(comment_lines) * FONT_SIZE + (len(comment_lines) - 1) * (6 * SCALE)))

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
        draw.text((cx + max(CELL_PAD_X, (col_w - h_w) // 2), ty + (HEADER_H - FONT_SIZE) // 2),
                  header, fill=HEADER_TEXT, font=font)
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
            draw.text((cx + CELL_PAD_X, cy + CELL_PAD_Y + li * (FONT_SIZE + 4 * SCALE)),
                      line, fill=TEXT_COLOR, font=font)
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
            logger.error(f"Telegram image send failed for chat {chat_id}: {e}")
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
            logger.error(f"Telegram text send failed for chat {chat_id}: {e}")
            sent = False
    return sent


def send_site_down_alert(threshold_min=None, incident_repository=None):
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

    rows = _site_down_over_threshold(threshold_min, incident_repository)
    if not rows:
        logger.info(f"No Incident Site Down over {threshold_min} minutes — nothing to send")
        return {"sent": False, "count": 0}

    photo = _render_table_image(rows, "Site Down Alerts")
    if photo:
        sent = _send_telegram_photo(token, chat_ids, photo)
    else:
        sent = _send_telegram_text(token, chat_ids, _format_message(rows, threshold_min))

    logger.info(f"Sent Telegram Site Down alert — {len(rows)} incident(s) to {len(chat_ids)} chat(s)")
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
    scheduler_utils.py for the shared loop/guard logic; `sleep_first=True`
    is what makes the first send happen after a full interval rather than
    immediately on startup (see module docstring above)."""
    wait = interval_seconds or app.config["ALERT_INTERVAL_SECONDS"]
    start_singleton_loop(
        app, _work, wait,
        thread_name="telegram-site-down-alert",
        log_message=f"Telegram Site Down alert scheduler started (every {wait}s)",
        sleep_first=True,
    )
