"""Background thread for the Site Down 24h Teams alert
(app/services/incident/site_down_24h_alert_service.py) — checks for new
down-over-24h incidents to alert, and separately for already-alerted
incidents that have since resolved, every
SITE_DOWN_24H_ALERT_INTERVAL_SECONDS. Both checks run in the same cycle
rather than two separate schedulers, since neither is expensive (small
local-cache reads + at most a handful of Teams POSTs) and they share
the same dedup ledger anyway.

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
# check it at startup — see that function's own docstring. Confirmed
# unused against every other scheduler's own OFFSET_SECONDS.
OFFSET_SECONDS = 120


def start(app, interval_seconds):
    tz_name = app.config["TIMEZONE"]

    def _work():
        down_sent = check_and_send_down_alerts()
        restore_sent = check_and_send_restore_alerts()
        total = down_sent + restore_sent
        if total:
            logger.info(
                f"Site Down 24h alert: {down_sent} down-alert(s), "
                f"{restore_sent} restore-confirmation(s) sent"
            )
        return total

    start_singleton_loop(
        app,
        _work,
        interval_seconds,
        thread_name="site-down-24h-alert",
        log_message=f"Site Down 24h alert scheduler started (every {interval_seconds}s)",
        first_run_delay=seconds_until_next_aligned_time(
            interval_seconds, tz_name, offset_seconds=OFFSET_SECONDS
        ),
        next_delay_fn=lambda: seconds_until_next_aligned_time(
            interval_seconds, tz_name, offset_seconds=OFFSET_SECONDS
        ),
    )
