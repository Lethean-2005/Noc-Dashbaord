"""Sends a Telegram alert listing every INC-WO Site Down row currently
open (INC_WO_ALERT_THRESHOLD_MIN defaults to 0 — every row, not just ones
open past a threshold), rendered as a table image (via Pillow) — same
rendering approach as app/services/telegram/telegram_alert.py, see that
module for the full "why an image, why sendDocument not sendPhoto"
reasoning. Unlike that module's Site Down alert (a "what's been open too
long" nudge, threshold 240min/4h), this one reads as "here's the current
INC-WO Site Down list right now", refreshed every
INC_WO_ALERT_INTERVAL_SECONDS (default 900s/15min) — set
INC_WO_ALERT_THRESHOLD_MIN above 0 in .env to go back to a threshold-only
alert instead.

Reads the already-synced inc_wo_site_down cache (see
app/repositories/incwo/incwo_status_cache_repository.py,
app/database/queries/inc_wo_site_down.sql) instead of querying Postgres
directly — kept fresh every INCIDENT_SYNC_INTERVAL_SECONDS by
IncidentSyncService. Every row read is also mirrored into the local
telegram_inc_wo_alert_cache table (a separate table from
telegram_alert.py's telegram_alert_cache — see
app/database/cache.py's comment for why) before the threshold filter
runs, so this alert's last run is inspectable independent of whether
anything was actually over-threshold.

Sent via a SEPARATE Telegram bot (TELEGRAM_BOT_INC_WO_TOKEN) to its OWN
chat/group (TELEGRAM_CHAT_IDS_INC_WO), independent of the Site Down
alert's TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_IDS above. Never runs unless both
TELEGRAM_BOT_INC_WO_TOKEN and TELEGRAM_CHAT_IDS_INC_WO are set. The bot
must also already be a member of that chat — Telegram returns "Bad
Request: chat not found" otherwise, even with a correct token/chat id.

start() runs this on its own background loop, once every
INC_WO_ALERT_INTERVAL_SECONDS (default 900s / 15min), clock-aligned the
same way telegram_alert.py's own loop is — offset by _OFFSET_SECONDS so
this and any other clock-aligned job landing on the same interval don't
all fire in the same instant (same "thundering herd" reasoning as every
other scheduler in app/services/scheduler_utils.py).
"""

import io
import os
from datetime import datetime

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
    _chat_ids,
    _format_outage,
    _send_telegram_text,
    _wrap_text_px,
)
from app.utils.datetime import elapsed_minutes
from app.utils.logger import get_logger

try:
    from PIL import Image, ImageDraw, ImageFont

    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

# Inter, not telegram_alert.py's Exo2-Bold or the dashboard's own Poppins
# — asked for specifically on this alert only, nothing else. Downloaded
# from Google Fonts' own repo (google/fonts, ofl/inter — OFL licensed,
# same self-hosting approach as every other font in app/static/fonts/).
# It's a variable font (weight axis) — set_variation_by_name("Bold") below
# pins it to the Bold weight explicitly, rather than relying on whatever
# the font's own default named instance happens to be (the filename says
# "Regular" only because that's the variable font file itself — the
# rendered weight is controlled entirely by set_variation_by_name()).
# Local to this module only — telegram_alert.py's own Site Down alert
# keeps its existing Exo2-Bold look, this change wasn't asked for there.
_FONT_PATH = os.path.join(_FONT_DIR, "Inter-Regular.ttf")

logger = get_logger(__name__)

_SITE_DOWN_TABLE = "inc_wo_site_down"
_CACHE_TABLE = "telegram_inc_wo_alert_cache"

# Staggers this alert's clock-aligned send time away from telegram_alert.py's
# own (which uses offset_seconds=0, i.e. lands exactly on the interval
# boundary) — see module docstring.
_OFFSET_SECONDS = 120


def _cache_telegram_rows(rows, cache_repository=None):
    """Mirror every fetched row into telegram_inc_wo_alert_cache — same
    replace-everything pattern telegram_alert.py's own _cache_telegram_rows()
    uses. Best-effort — a cache write failure shouldn't stop the alert
    itself from being evaluated/sent."""
    cache_repository = cache_repository or TelegramIncWoAlertCacheRepository()
    try:
        cache_repository.replace_all(_CACHE_TABLE, rows)
    except Exception as e:
        logger.error(f"telegram_inc_wo_alert_cache write failed: {e}")


def _inc_wo_site_down_over_threshold(
    threshold_min, status_cache_repository=None, cache_repository=None
):
    """Every INC-WO Site Down row (per inc_wo_site_down.sql) whose
    outage_min — minutes since the WO was created, not since the
    incident occurred, since a WO can be created well after its incident
    — has passed `threshold_min` minutes, longest-open first. outage_min
    is computed for every row (not just the ones over threshold) before
    caching, same convention as telegram_alert.py's own
    _site_down_over_threshold()."""
    status_cache_repository = status_cache_repository or IncWoStatusCacheRepository()
    rows = status_cache_repository.fetch_all(_SITE_DOWN_TABLE)
    for row in rows:
        row["outage_min"] = elapsed_minutes(row.get("wo_created_at"))
    _cache_telegram_rows(rows, cache_repository)

    over_threshold = [row for row in rows if row["outage_min"] >= threshold_min]
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


# (header, char width, row key) — one entry per column, in display order,
# matching the dashboard's own INC-WO Site Down drilldown/CSV column order
# exactly, all in one row per record (per explicit request — the earlier
# two-line-per-record layout was reverted). "Fault Description" is the
# one wrapped, multi-line column (_WRAP_COLUMN_INDEX below).
_COLUMNS = (
    ("Incident ID", 16, "incident_id"),
    ("INC-WO ID", 20, "wo_id"),
    ("INC-WO Created At", 16, "wo_created_at"),
    ("INC-WO Status", 14, "wo_status"),
    ("Site Name", 14, "site_name"),
    ("Site Code", 8, "site_code"),
    ("Overdue", 8, "overdue"),
    ("Support Level", 18, "support_level"),
    ("Fault Description", 40, "fault_description"),
    ("NMS", 8, "nms"),
    ("Hub Site", 12, "hub_site"),
    ("Site Grade", 10, "site_grade"),
    ("Province", 14, "province"),
    ("District", 16, "district"),
    ("Commune", 18, "commune"),
)
_WRAP_COLUMN_INDEX = 8  # "Fault Description" — the only multi-line column
_STATUS_COLUMN_INDEX = 3  # "INC-WO Status" — the only color-coded column

# Same colors as the dashboard's own status badge
# (app/static/css/components/status_links.css's .status-badge.status-*
# rules / app/utils/formatter.py's status_badge_class()), so "In
# Progress"/"Acknowledged"/etc. read the same way here as they do on
# screen. Falls back to plain black text for any status not in this map.
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


def _render_inc_wo_table_image(rows, title):
    """Same rendering approach as telegram_alert.py's _render_table_image()
    (same fonts/colors/layout constants, kept in that module and reused
    here so the two alerts' images look identical apart from their
    columns) — full column set per _COLUMNS above, one row per record,
    matching the dashboard's own INC-WO Site Down table/CSV column order.
    Text is sized larger than telegram_alert.py's own table for
    readability, since this table has almost twice as many columns.
    INC-WO Status is colored per _STATUS_COLORS, matching the dashboard's
    own status badge colors, so "In Progress"/"Acknowledged"/etc. read the
    same way here as on screen. Returns PNG bytes, or None if Pillow/the
    font isn't available (caller falls back to plain text)."""
    if not _HAS_PIL or not os.path.exists(_FONT_PATH):
        return None

    # SCALE=1, not telegram_alert.py's 2 — that alert's table has 8 columns,
    # this one has 15, and at SCALE=2 the accumulated width became so
    # extreme (25000+ px for just a couple of rows, 2+ MB per send) that
    # Telegram's own document-preview thumbnail squashed it into an
    # unreadable blur (confirmed live via a real sent file). SCALE=1 keeps
    # every font-size/weight/color choice exactly as sized in points —
    # just rendered at a saner total pixel count, so the file stays a
    # reasonable size and the aspect ratio isn't so extreme that Telegram's
    # thumbnail generator falls over. The full image is still sharp when
    # actually opened either way — this only affects the preview thumbnail
    # and the file size, not text quality once opened.
    SCALE = 1
    FONT_SIZE, TITLE_SIZE = 56 * SCALE, 62 * SCALE
    CELL_PAD_X, CELL_PAD_Y = 26 * SCALE, 26 * SCALE
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
    font.set_variation_by_name("Bold")
    title_font = ImageFont.truetype(_FONT_PATH, TITLE_SIZE)
    title_font.set_variation_by_name("Bold")
    char_w = int(font.getlength("M"))

    headers = [c[0] for c in _COLUMNS]
    col_w_px = [chars * char_w + CELL_PAD_X * 2 for _, chars, _ in _COLUMNS]
    table_w = sum(col_w_px)

    data_rows, row_heights = [], []
    for row in rows:
        values = []
        for ci, (_header, _chars, key) in enumerate(_COLUMNS):
            if ci == _WRAP_COLUMN_INDEX:
                text = (row.get(key) or "").replace("\n", " ").strip()
                values.append(_wrap_text_px(text, font, col_w_px[ci] - CELL_PAD_X * 2)[:5])
            elif key == "wo_created_at":
                values.append((row.get(key) or "")[:16])
            else:
                values.append(str(row.get(key) or "—"))
        data_rows.append(values)
        wrap_lines = values[_WRAP_COLUMN_INDEX]
        row_heights.append(
            max(
                BASE_ROW_H,
                CELL_PAD_Y * 2 + len(wrap_lines) * FONT_SIZE + (len(wrap_lines) - 1) * (6 * SCALE),
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
        for ci, col_w in enumerate(col_w_px):
            if ci == _WRAP_COLUMN_INDEX:
                for li, line in enumerate(values[ci]):
                    draw.text(
                        (cx + CELL_PAD_X, cy + CELL_PAD_Y + li * (FONT_SIZE + 4 * SCALE)),
                        line,
                        fill=TEXT_COLOR,
                        font=font,
                    )
            else:
                color = TEXT_COLOR
                if ci == _STATUS_COLUMN_INDEX:
                    color = _STATUS_COLORS.get(values[ci], TEXT_COLOR)
                draw.text(
                    (cx + CELL_PAD_X, cy + (row_h - FONT_SIZE) // 2),
                    values[ci],
                    fill=color,
                    font=font,
                )
            cx += col_w
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


def _send_telegram_document(token, chat_ids, photo_bytes):
    """Same "send as a document, not sendPhoto" reasoning as
    telegram_alert.py's own _send_telegram_photo() (Telegram recompresses
    photos, which blurs small table text; documents are delivered
    untouched) — but with its own filename, "inc-wo-site-down-alert.png",
    instead of reusing that function and its hardcoded "site-down-
    alert.png". Confirmed live: without this, Telegram Desktop shows both
    alerts' files under the identical name, indistinguishable from each
    other in the chat."""
    url = _TELEGRAM_SEND_DOCUMENT_URL.format(token=token)
    sent = True
    for chat_id in chat_ids:
        try:
            files = {"document": ("inc-wo-site-down-alert.png", photo_bytes, "image/png")}
            resp = requests.post(url, files=files, data={"chat_id": chat_id}, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Telegram image send failed for chat {chat_id}: {e}")
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

    logger.info(
        f"Sent Telegram INC-WO Site Down alert — {len(rows)} row(s) to {len(chat_ids)} chat(s)"
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
    """Start the background alert loop, once per process. See
    telegram_alert.py's start() for the full first_run_delay/next_delay_fn
    reasoning — same pattern here, just offset by _OFFSET_SECONDS so this
    alert and the Site Down one don't both fire at the same aligned
    instant."""
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
