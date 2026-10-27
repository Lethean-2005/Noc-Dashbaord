"""Background threads for the Site Down 24h Teams alert
(app/services/incident/site_down_24h_alert_service.py) — two
INDEPENDENTLY timed loops, not one shared cycle:

  - down-alert check, every SITE_DOWN_24H_ALERT_INTERVAL_SECONDS
    (24h by default) — only needs to catch an incident shortly after
    it crosses the threshold, not continuously.
  - restore-confirmation check, every
    SITE_DOWN_24H_ALERT_RESTORE_INTERVAL_SECONDS (15min by default) —
    a restore should be noticed soon after it actually happens, not
    wait for the same once-a-day cadence the down-alert check uses.

Split into two loops (not one shared `_work()` like before) specifically
so these two intervals can differ — confirmed needed live: forcing them
to share one interval meant slowing the down-alert check down to 24h
(to cut Teams/SharePoint call volume) also slowed restore-confirmation
down to 24h, adding up to a full day of delay after a site actually
came back up.

start() is called once from app/__init__.py::create_app(). See
scheduler_utils.py for the shared loop/guard logic.
"""

from app.services.incident.site_down_24h_alert_service import (
    check_and_send_down_alerts,
    check_and_send_restore_alerts,
)
from app.services.scheduler_utils import seconds_until_next_aligned_time, start_singleton_loop
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Module-level so app/__init__.py's _validate_scheduler_offsets() can
# check both at startup — see that function's own docstring. Two
# separate constants (not one) since this module now runs two
# independently-timed loops that could otherwise land on the exact
# same instant as each other, or as some other scheduler.
OFFSET_SECONDS = 120
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
