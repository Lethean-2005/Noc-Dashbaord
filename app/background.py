"""Background job registration for the dedicated worker process."""
from importlib import import_module

_SCHEDULER_OFFSET_MODULES = (
    "app.services.alarm.alarm_scheduler",
    "app.services.alarm.congestion_history_scheduler",
    "app.services.site.site_scheduler",
    "app.services.site.site_lookup_scheduler",
    "app.services.incident.incident_scheduler",
    "app.services.ape_alarm.ape_alarm_scheduler",
    "app.services.vip.vip_alarm_scheduler",
    "app.services.vip.vip_site_scheduler",
    "app.services.pop.pop_scheduler",
    "app.services.site.mssql_site_onair_scheduler",
    "app.services.partner_contact.partner_contact_scheduler",
    "app.services.incident.site_down_24h_alert_scheduler",
)


def _validate_scheduler_offsets():
    """Fails app startup loudly if two schedulers in
    _SCHEDULER_OFFSET_MODULES share the same OFFSET_SECONDS — the exact
    bug behind a real production incident (2026-10-06):
    partner_contact_scheduler.py and mssql_site_onair_scheduler.py both
    used offset_seconds=110 with the same 300s interval, so they launched
    at the identical instant every cycle, piled up writing to the shared
    SQLite cache at once, and several OTHER schedulers' writes queued up
    behind that collision and failed outright ("database is locked")
    after 58-123s instead of the normal <1s. That went undetected for
    weeks because nothing checked it.

    Called unconditionally from create_app() — including under pytest,
    not just a real app boot — so a repeat of this exact mistake fails
    the test suite immediately instead of silently reaching production
    again."""
    seen = {}
    for module_path in _SCHEDULER_OFFSET_MODULES:
        offset = import_module(module_path).OFFSET_SECONDS
        if offset in seen:
            raise RuntimeError(
                f"Scheduler offset collision: {module_path!r} and {seen[offset]!r} "
                f"both use OFFSET_SECONDS={offset}. Two schedulers sharing an "
                "offset launch at the exact same instant every cycle and pile up "
                "writing to the same SQLite cache file at once — this caused a "
                "real production incident on 2026-10-06 (partner_contact_scheduler.py "
                "vs mssql_site_onair_scheduler.py, both offset=110). Pick a value "
                "not already used by any other entry in _SCHEDULER_OFFSET_MODULES."
            )
        seen[offset] = module_path

    # site_down_24h_alert_scheduler runs TWO independently-timed loops
    # (down-alert + restore-confirmation) sharing one module, so it needs
    # a second offset checked here too — its own OFFSET_SECONDS (the
    # down-alert loop) was already checked by the generic loop above.
    from app.services.incident import site_down_24h_alert_scheduler as _sd24h

    restore_offset = _sd24h.RESTORE_OFFSET_SECONDS
    if restore_offset in seen:
        raise RuntimeError(
            "Scheduler offset collision: site_down_24h_alert_scheduler's own "
            f"RESTORE_OFFSET_SECONDS={restore_offset} collides with "
            f"{seen[restore_offset]!r}. Pick a value not already used by any "
            "other entry in _SCHEDULER_OFFSET_MODULES."
        )
    seen[restore_offset] = "app.services.incident.site_down_24h_alert_scheduler (restore loop)"


# (scheduler module, config key holding its interval in seconds) — every
# entry here used to be its own near-identical _init_*_cache() function
# (~100 lines total) repeating the same testing/debug-reloader skip-guard
# by hand. Registered by start_worker_jobs() below; add a domain's
# background sync here instead of writing a new function for it.
_BACKGROUND_JOBS = (
    ("app.services.alarm.alarm_scheduler", "MSSQL_SYNC_INTERVAL_SECONDS"),
    ("app.services.alarm.congestion_history_scheduler", "CONGESTION_SYNC_INTERVAL_SECONDS"),
    ("app.services.site.site_scheduler", "SITE_SYNC_INTERVAL_SECONDS"),
    ("app.services.site.site_lookup_scheduler", "SITE_LOOKUP_SYNC_INTERVAL_SECONDS"),
    ("app.services.incident.incident_scheduler", "INCIDENT_SYNC_INTERVAL_SECONDS"),
    ("app.services.ape_alarm.ape_alarm_scheduler", "APE_ALARM_SYNC_INTERVAL_SECONDS"),
    ("app.services.vip.vip_alarm_scheduler", "VIP_ALARM_SYNC_INTERVAL_SECONDS"),
    ("app.services.vip.vip_site_scheduler", "VIP_SITE_SYNC_INTERVAL_SECONDS"),
    ("app.services.pop.pop_scheduler", "POP_SYNC_INTERVAL_SECONDS"),
    ("app.services.site.mssql_site_onair_scheduler", "MSSQL_SITE_ONAIR_SYNC_INTERVAL_SECONDS"),
    ("app.services.partner_contact.partner_contact_scheduler", "PARTNER_CONTACT_SYNC_INTERVAL_SECONDS"),
    ("app.services.incident.site_down_24h_alert_scheduler", "SITE_DOWN_24H_ALERT_INTERVAL_SECONDS"),
    ("app.services.all_tasks_scheduler", "ALL_TASKS_SUMMARY_INTERVAL_SECONDS"),
    ("app.routes.dashboard", "DASHBOARD_LOG_INTERVAL_SECONDS"),
)




_ALERT_JOBS = (
    ("app.services.telegram.telegram_alert", "ALERT_INTERVAL_SECONDS", ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_IDS")),
    ("app.services.telegram.telegram_inc_wo_alert", "INC_WO_ALERT_INTERVAL_SECONDS", ("TELEGRAM_BOT_INC_WO_TOKEN", "TELEGRAM_CHAT_IDS_INC_WO")),
    ("app.services.telegram.telegram_inc_wo_power_alert", "INC_WO_POWER_ALERT_INTERVAL_SECONDS", ("TELEGRAM_BOT_INC_WO_POWER_TOKEN", "TELEGRAM_CHAT_IDS_INC_WO_POWER")),
    ("app.services.telegram.telegram_inc_wo_general_alert", "INC_WO_GENERAL_ALERT_INTERVAL_SECONDS", ("TELEGRAM_BOT_INC_WO_GENERAL_TOKEN", "TELEGRAM_CHAT_IDS_INC_WO_GENERAL")),
    ("webhook", "TEAMS_ALERT_INTERVAL_SECONDS", ("TEAMS_ALERTS_ENABLED",)),
)


def configured_jobs(config):
    """Return enabled jobs without changing their existing intervals or gates."""
    jobs = list(_BACKGROUND_JOBS)
    jobs.extend((module, key) for module, key, required in _ALERT_JOBS
                if all(config.get(name) for name in required))
    return jobs


def start_worker_jobs(app):
    if app.config.get("PROCESS_ROLE") != "worker":
        raise RuntimeError("Scheduled jobs require the dedicated worker process")
    _validate_scheduler_offsets()
    jobs = configured_jobs(app.config)
    for _, key in jobs:
        if app.config[key] <= 0:
            raise ValueError(f"{key} must be positive")
    for module, key in jobs:
        import_module(module).start(app, app.config[key])
