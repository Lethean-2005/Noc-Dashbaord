"""Sends a Telegram alert listing every open INC-WO row EXCEPT
category='site_down'/'power' (those two already have their own dedicated
alerts — telegram_inc_wo_alert.py, telegram_inc_wo_power_alert.py),
rendered as a table image — a near-exact copy of
telegram_inc_wo_power_alert.py. See that module and telegram_alert.py for
the full image/sendDocument reasoning. Telegram-only — no dashboard card
reads inc_wo_by_status for this purpose.

Unlike the Site Down/Power alerts, this one has no dedicated source query
of its own — it reads the already-synced inc_wo_by_status cache (every
INC-WO not yet closed, every category, including Resolved ones) and
excludes Site Down/Power categories plus Resolved status here in Python
instead, rather than adding a fourth near-identical SQL
query/cache-table/sync-method purely to pre-filter what this alert alone
reads. Every row read (before that exclusion) is mirrored into
telegram_inc_wo_general_alert_cache (its own table, so it can't overwrite
another alert's last-run snapshot) before the threshold filter runs.

Every send also attaches a second document: every over-threshold row (not
chunked, unlike the images) as a styled .xlsx — see telegram_alert.py's
_build_excel_bytes().

Sent via its own bot/chat (TELEGRAM_BOT_INC_WO_GENERAL_TOKEN /
TELEGRAM_CHAT_IDS_INC_WO_GENERAL) — never runs unless both are set, and the
bot must already be a member of that chat.

start() runs this on its own background loop, clock-aligned, deliberately
landing at the exact same instant as every other Telegram alert
(_OFFSET_SECONDS=0 on all of them, per explicit request).
"""

import requests
from flask import current_app

from app.repositories.incwo.incwo_status_cache_repository import IncWoStatusCacheRepository
from app.repositories.telegram.telegram_inc_wo_general_alert_cache_repository import (
    TelegramIncWoGeneralAlertCacheRepository,
)
from app.services.scheduler_utils import seconds_until_next_aligned_time, start_singleton_loop
from app.services.telegram.telegram_alert import (
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
from app.services.telegram.telegram_inc_wo_alert import (
    _EXCEL_COLUMNS,
    _EXCEL_LEFT_ALIGN_HEADERS,
    _STATUS_COLORS,
    _is_priority_site,
    _render_inc_wo_table_image,
)
from app.utils.datetime import elapsed_minutes
from app.utils.logger import get_logger

logger = get_logger(__name__)

_STATUS_TABLE = "inc_wo_by_status"
_CACHE_TABLE = "telegram_inc_wo_general_alert_cache"

# incident_category values that already have their own dedicated Telegram
# alert (telegram_inc_wo_alert.py, telegram_inc_wo_power_alert.py) — this
# alert is "everything else". Matched against inc_wo_by_status's
# "Incident Category" column, which sql_loader/Postgres already renders as
# INITCAP'd Title Case (e.g. "Site Down", not "site_down").
_EXCLUDED_CATEGORIES = {"Site Down", "Power"}

# One image per this many rows — same reasoning as
# telegram_inc_wo_power_alert.py's own _MAX_ROWS_PER_IMAGE.
_MAX_ROWS_PER_IMAGE = 25

# 0 — lands exactly on the interval boundary (:00/:15/:30/:45), same as
# every other Telegram alert. Deliberately NOT staggered — see
# telegram_inc_wo_alert.py's own _OFFSET_SECONDS comment for why that's
# safe for these lightweight cache-read-then-POST alerts.
_OFFSET_SECONDS = 0


def _cache_telegram_rows(rows, cache_repository=None):
    """Mirror every fetched row into telegram_inc_wo_general_alert_cache —
    same replace-everything pattern telegram_inc_wo_alert.py's own
    _cache_telegram_rows() uses. Best-effort — a cache write failure
    shouldn't stop the alert itself from being evaluated/sent."""
    cache_repository = cache_repository or TelegramIncWoGeneralAlertCacheRepository()
    try:
        cache_repository.replace_all(_CACHE_TABLE, rows)
    except Exception as e:
        logger.error(f"telegram_inc_wo_general_alert_cache write failed: {e}")


def _inc_wo_general_over_threshold(threshold_min, status_cache_repository=None, cache_repository=None):
    """Rows whose outage_min has passed `threshold_min`, longest-open
    first — same shape as telegram_inc_wo_power_alert.py's own
    _inc_wo_category_power_over_threshold(), plus two extra exclusions
    inc_wo_by_status doesn't already apply for us: Site Down/Power
    categories (those have their own alerts) and Resolved status
    (inc_wo_by_status, unlike the dedicated Site Down/Power tables, keeps
    Resolved rows — see module docstring)."""
    status_cache_repository = status_cache_repository or IncWoStatusCacheRepository()
    rows = status_cache_repository.fetch_all(_STATUS_TABLE)
    for row in rows:
        row["outage_min"] = elapsed_minutes(row.get("wo_created_at"))
    _cache_telegram_rows(rows, cache_repository)

    over_threshold = [
        row
        for row in rows
        if row.get("wo_id")
        and row["outage_min"] >= threshold_min
        and _is_l2_support(row)
        and row.get("incident_category") not in _EXCLUDED_CATEGORIES
        and (row.get("wo_status") or "").strip().upper() != "RESOLVED"
    ]
    over_threshold.sort(key=lambda row: row["outage_min"], reverse=True)
    return over_threshold


def _format_message(rows, threshold_min):
    """Plain-text fallback, used only if Pillow/the font can't render an
    image (e.g. a stripped-down deploy without Pillow installed)."""
    hours = threshold_min // 60
    lines = [f"INC-WO Alert — open over {hours}h ({len(rows)})", ""]
    for row in rows:
        site = row.get("site_name") or row.get("site_code") or "Unknown site"
        lines.append(
            f"• {row.get('wo_id') or row.get('incident_id')} — {site} "
            f"— {_format_outage(row['outage_min'])} — {row.get('province') or 'Unknown province'}"
        )
    return "\n".join(lines)


def _send_telegram_document(token, chat_ids, photo_bytes):
    """Same "send as a document, not sendPhoto" reasoning as
    telegram_alert.py's own _send_telegram_photo() — its own filename,
    "Inc-wo-alert.png", keeps it distinct from the other three Telegram
    alerts in Telegram Desktop."""
    url = _TELEGRAM_SEND_DOCUMENT_URL.format(token=token)
    sent = True
    for chat_id in chat_ids:
        try:
            files = {"document": ("Inc-wo-alert.png", photo_bytes, "image/png")}
            resp = requests.post(url, files=files, data={"chat_id": chat_id}, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Telegram image send failed for chat {chat_id}: {_error_detail(e)}")
            sent = False
    return sent


def send_inc_wo_general_alert(threshold_min=None, status_cache_repository=None, cache_repository=None):
    """Send a Telegram alert listing every INC-WO (except site_down/power)
    whose WO has been open past `threshold_min` (defaults to
    app.config['INC_WO_GENERAL_ALERT_THRESHOLD_MIN']) — as one or more
    table images (split into _MAX_ROWS_PER_IMAGE-row chunks, each its own
    "Part X/Y" image/send), or plain text per chunk if Pillow/the font
    isn't available. Returns {'sent': bool, 'count': int} — count is the
    total row count across every chunk. Raises EnvironmentError if
    TELEGRAM_BOT_INC_WO_GENERAL_TOKEN/TELEGRAM_CHAT_IDS_INC_WO_GENERAL
    aren't configured — callers decide whether that's fatal or just a
    skip."""
    token = current_app.config["TELEGRAM_BOT_INC_WO_GENERAL_TOKEN"]
    chat_ids = _chat_ids(current_app.config["TELEGRAM_CHAT_IDS_INC_WO_GENERAL"])
    if not token or not chat_ids:
        raise EnvironmentError(
            "TELEGRAM_BOT_INC_WO_GENERAL_TOKEN and TELEGRAM_CHAT_IDS_INC_WO_GENERAL must be set in .env"
        )

    if threshold_min is None:
        threshold_min = current_app.config["INC_WO_GENERAL_ALERT_THRESHOLD_MIN"]

    rows = _inc_wo_general_over_threshold(threshold_min, status_cache_repository, cache_repository)
    if not rows:
        logger.info(f"No INC-WO General over {threshold_min} minutes — nothing to send")
        return {"sent": False, "count": 0}

    chunks = [
        rows[i : i + _MAX_ROWS_PER_IMAGE] for i in range(0, len(rows), _MAX_ROWS_PER_IMAGE)
    ]
    sent = True
    if len(chunks) > 1:
        sent = _send_telegram_text(token, chat_ids, f"INC-WO Alert — {len(chunks)} Part(s)") and sent
    for i, chunk in enumerate(chunks, start=1):
        title = "INC-WO Alerts"
        if len(chunks) > 1:
            title += f" (Part {i}/{len(chunks)})"
        photo = _render_inc_wo_table_image(chunk, title)
        if photo:
            sent = _send_telegram_document(token, chat_ids, photo) and sent
        else:
            sent = _send_telegram_text(token, chat_ids, _format_message(chunk, threshold_min)) and sent

    excel = _build_excel_bytes(
        _EXCEL_COLUMNS,
        rows,
        "INC-WO Alerts",
        status_key="INC-WO Status",
        status_colors=_STATUS_COLORS,
        priority_fn=_is_priority_site,
        hyperlinks={"Incident ID": _incident_link, "INC-WO ID": _inc_wo_link},
        left_align=_EXCEL_LEFT_ALIGN_HEADERS,
    )
    if excel:
        sent = _send_telegram_excel(token, chat_ids, excel, "Inc-wo-alert.xlsx") and sent

    logger.info(
        f"Sent Telegram INC-WO General alert — {len(rows)} row(s) in {len(chunks)} "
        f"image(s) to {len(chat_ids)} chat(s)"
    )
    return {"sent": sent, "count": len(rows)}


def _work():
    try:
        send_inc_wo_general_alert()
    except EnvironmentError as e:
        logger.error(f"Telegram INC-WO General alert not configured: {e}")
    except Exception as e:
        logger.error(f"Telegram INC-WO General alert failed: {e}")


def start(app, interval_seconds=None):
    """Start the background alert loop, once per process — see
    telegram_alert.py's start() for the first_run_delay/next_delay_fn
    reasoning."""
    wait = interval_seconds or app.config["INC_WO_GENERAL_ALERT_INTERVAL_SECONDS"]
    tz_name = app.config["TIMEZONE"]
    delay = seconds_until_next_aligned_time(wait, tz_name, offset_seconds=_OFFSET_SECONDS)
    start_singleton_loop(
        app,
        _work,
        wait,
        thread_name="telegram-inc-wo-general-alert",
        log_message=f"Telegram INC-WO General alert scheduler started (every {wait}s, "
        f"first run in {delay:.0f}s)",
        first_run_delay=delay,
        next_delay_fn=lambda: seconds_until_next_aligned_time(
            wait, tz_name, offset_seconds=_OFFSET_SECONDS
        ),
    )
