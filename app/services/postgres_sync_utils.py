"""Shared helpers for sync services that pull from PostgreSQL.

Fetch-retry, UTC->local timestamp conversion, and the standard_code site
lookup used to be copy-pasted identically across ape_alarm_sync_service.py,
vip_alarm_sync_service.py, and incident_sync_service.py — factored here so a
future tuning change (retry budget, timezone handling) only needs to happen
once instead of in three files kept in lockstep by hand.
"""
import time
from datetime import timezone
from zoneinfo import ZoneInfo

from flask import current_app

from app.utils.logger import get_logger

logger = get_logger(__name__)

FETCH_MAX_ATTEMPTS = 6
FETCH_MAX_RETRY_DELAY_SECONDS = 30


def retry_fetch(fetch_fn, label, max_attempts=FETCH_MAX_ATTEMPTS, max_delay_seconds=FETCH_MAX_RETRY_DELAY_SECONDS):
    """Calls fetch_fn() with retry + capped exponential backoff on failure
    (2s, 4s, 8s, 16s, 30s, ...) — mitigates "conflict with recovery" (the
    hot-standby replica's WAL-replay race) without hammering the replica on
    a longer-lived conflict. Returns None (and logs) if every attempt
    fails; callers must check for None and return early.

    Every outcome is logged (see app/utils/logger.py's ATTEMPT/SUCCESS/
    FAILED handling and logs/attempts.log): a warning per failed attempt, a
    "sync succeeded on attempt N/M, got R row(s) in X.XXs" info line on
    success — timed from the very first attempt, so it reflects the full
    cost of any retries it took to get there, not just the winning call —
    and an error once every attempt is exhausted."""
    start = time.monotonic()
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = fetch_fn()
        except Exception as e:
            last_error = e
            if attempt < max_attempts:
                wait = min(2 ** attempt, max_delay_seconds)
                logger.warning(
                    f"Postgres {label} sync attempt {attempt}/{max_attempts} failed, "
                    f"retrying in {wait}s: {e}"
                )
                time.sleep(wait)
        else:
            elapsed = time.monotonic() - start
            logger.info(
                f"Postgres {label} sync succeeded on attempt {attempt}/{max_attempts}, "
                f"got {len(result)} row(s) in {elapsed:.2f}s"
            )
            return result
    logger.error(f"Postgres {label} sync failed after {max_attempts} attempts: {last_error}")
    return None


def to_local_seconds(value):
    """Postgres hands these back as UTC (no session timezone is set on this
    connection), while Streamline's own UI displays them already converted
    to local time. Without this, every cached timestamp — and every
    Outage(min) figure computed from one via app/utils/datetime.py's
    elapsed_minutes(), which compares against the machine's local clock —
    would be off by the local UTC offset (7 hours for Asia/Phnom_Penh)."""
    if not value:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    local_tz = ZoneInfo(current_app.config["TIMEZONE"])
    return value.astimezone(local_tz).strftime("%Y-%m-%d %H:%M:%S")


def build_site_lookup(site_cache_repository, table):
    """standard_code -> site_cache row, so Site Name/Site Strategic Type can
    be resolved locally instead of joining site_cache's source table in
    Postgres."""
    try:
        site_rows = site_cache_repository.fetch_all(table)
    except Exception as e:
        logger.error(f"Reading {table} failed: {e}")
        return {}
    return {row["standard_code"]: row for row in site_rows if row.get("standard_code")}
