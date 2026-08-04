"""
webhook — one Teams / Power-Automate webhook sender per alarm type.

Each alarm type is a module (webhook/<name>.py) exposing a `SPEC`. Shared card /
send logic lives in webhook/common.py. Every webhook reads its own URL from
`.env`; an unset URL means that webhook is simply skipped.

  python -m webhook                          # send all configured webhooks
  python webhook/dg_on.py --dry-run          # preview one

start() runs send_all() on a background loop every TEAMS_ALERT_INTERVAL_SECONDS
(default 900s / 15 min) — called once from app/__init__.py::create_app(), same
pattern as app/services/telegram/telegram_alert.py's own start().
"""
from . import (eze_alarm, tct_alarm, pop_down, pop_main_failure, main_failure,
               current_site_down, cso_sub_con, current_site_outage, dg_on,
               inc_wo_site)

from app.services.scheduler_utils import seconds_until_next_aligned_time, start_singleton_loop
from app.utils.logger import get_logger

logger = get_logger(__name__)

# All alert specs, in send order.
SPECS = [m.SPEC for m in (
    eze_alarm, tct_alarm, pop_down, pop_main_failure, main_failure,
    current_site_down, cso_sub_con, current_site_outage, dg_on, inc_wo_site,
)]


def send_all() -> list[dict]:
    """Send every configured webhook (skips only those with no URL). Alerts with
    no active data still post a 'no active alarms' card only if
    WEBHOOK_SEND_EMPTY=true. Called by the scheduler and the CLI's send-all.
    Returns a list of per-webhook result dicts."""
    from webhook.common import send
    results = []
    for spec in SPECS:
        try:
            res = send(spec)
        except Exception as e:
            logger.error(f"webhook '{spec.key}' failed: {e}")
            res = {"sent": False, "count": 0, "status": None, "reason": str(e)}
        res["key"] = spec.key
        results.append(res)
    return results


def _work():
    results = send_all()
    sent = [r for r in results if r["sent"]]
    if sent:
        logger.info(f"Sent {len(sent)} Teams alert(s): {', '.join(r['key'] for r in sent)}")


def start(app, interval_seconds=None):
    """Start the background Teams alert loop, once per process. See
    app/services/scheduler_utils.py for the shared loop/guard logic; the
    computed first_run_delay lands the first send on a clean clock boundary
    (e.g. 900s -> :00/:15/:30/:45) instead of immediately on startup, same
    reasoning as telegram_alert.py's own start()."""
    wait = interval_seconds or app.config["TEAMS_ALERT_INTERVAL_SECONDS"]
    tz_name = app.config["TIMEZONE"]
    delay = seconds_until_next_aligned_time(wait, tz_name)
    start_singleton_loop(
        app, _work, wait,
        thread_name="teams-webhook-alerts",
        log_message=f"Teams webhook alert scheduler started (every {wait}s, "
                     f"first run in {delay:.0f}s)",
        first_run_delay=delay,
        next_delay_fn=lambda: seconds_until_next_aligned_time(wait, tz_name),
    )


__all__ = ["send_all", "start", "SPECS"]
