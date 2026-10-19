"""Background thread that keeps the local partner_contact_cache
(instance/localstorage.db) in sync — pulled straight from MSSQL's
TBL_PARTNER / TBL_PARTNER_CONTACT (see partner_contact_sync_service.py).
Runs on its own interval (PARTNER_CONTACT_SYNC_INTERVAL_SECONDS).

start() is called once from app/__init__.py::create_app(). See
scheduler_utils.py for the shared loop/guard logic.
"""

from app.services.partner_contact.partner_contact_sync_service import (
    PartnerContactSyncService,
)
from app.services.scheduler_utils import seconds_until_next_aligned_time, start_singleton_loop

# Was 110 until a real production incident (log dated 2026-10-06
# 10:57-10:58) showed this scheduler and mssql_site_onair_scheduler.py
# BOTH using offset_seconds=110 with the SAME 300s interval, so they
# launched at the exact same instant every single cycle, forever — not a
# rare fluke. Both then piled up writing to the same SQLite file at once;
# several OTHER schedulers' writes queued up behind that collision and
# ultimately failed outright ("database is locked") after 58-123s, well
# past the normal <1s sync time. Module-level (not inline in start())
# so app/__init__.py's own _validate_scheduler_offsets() can check every
# scheduler's offset at startup and fail loudly if this ever collides
# again, instead of silently causing a repeat of that incident in
# production weeks or months later.
OFFSET_SECONDS = 90


def start(app, interval_seconds):
    service = PartnerContactSyncService()
    tz_name = app.config["TIMEZONE"]

    def _work():
        return service.sync()

    start_singleton_loop(
        app,
        _work,
        interval_seconds,
        thread_name="partner-contact-cache-sync",
        log_message=f"Partner contact cache sync scheduler started (every {interval_seconds}s)",
        first_run_delay=seconds_until_next_aligned_time(
            interval_seconds, tz_name, offset_seconds=OFFSET_SECONDS
        ),
        next_delay_fn=lambda: seconds_until_next_aligned_time(
            interval_seconds, tz_name, offset_seconds=OFFSET_SECONDS
        ),
    )
