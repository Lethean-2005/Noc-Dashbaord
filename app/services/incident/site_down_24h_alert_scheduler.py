"""Separate Site Down and restoration loops, both defaulting to five minutes.

Intervals come from application configuration. Runs align to Cambodia time;
startup waits until each loop's next scheduled boundary.
"""

from app.services.incident.site_down_24h_alert_service import (
    check_and_send_down_alerts,
    check_and_send_restore_alerts,
)
from app.services.scheduler_utils import seconds_until_next_aligned_time, start_singleton_loop
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Distinct clock offsets keep the two checks staggered.
OFFSET_SECONDS = 43200
RESTORE_OFFSET_SECONDS = 50


def start(app, interval_seconds):
    tz_name = app.config["TIMEZONE"]
    restore_interval_seconds = app.config["SITE_DOWN_24H_ALERT_RESTORE_INTERVAL_SECONDS"]

    def _down_work():
        sent = check_and_send_down_alerts()
        if sent:
            logger.info(f"Site Down 24h: {sent} down-alert(s) sent")
        return sent

    def _restore_work():
        sent = check_and_send_restore_alerts()
        if sent:
            logger.info(f"Site Down 24h: {sent} restore-confirmation(s) sent")
        return sent

    start_singleton_loop(
        app,
        _down_work,
        interval_seconds,
        thread_name="site-down-24h-alert-down",
        log_message=f"Site Down 24h down-alert scheduler started (every {interval_seconds}s)",
        first_run_delay=seconds_until_next_aligned_time(
            interval_seconds, tz_name, offset_seconds=OFFSET_SECONDS
        ),
        next_delay_fn=lambda: seconds_until_next_aligned_time(
            interval_seconds, tz_name, offset_seconds=OFFSET_SECONDS
        ),
    )
    start_singleton_loop(
        app,
        _restore_work,
        restore_interval_seconds,
        thread_name="site-down-24h-alert-restore",
        log_message=(
            f"Site Down 24h restore-confirmation scheduler started "
            f"(every {restore_interval_seconds}s)"
        ),
        first_run_delay=seconds_until_next_aligned_time(
            restore_interval_seconds, tz_name, offset_seconds=RESTORE_OFFSET_SECONDS
        ),
        next_delay_fn=lambda: seconds_until_next_aligned_time(
            restore_interval_seconds, tz_name, offset_seconds=RESTORE_OFFSET_SECONDS
        ),
    )
