"""Run one configured Telegram alert without starting background schedulers.

Normal invocation sends REAL messages. --dry-run checks the packaged runner
and configuration only; it never calls a send function or writes the cache.
"""
import argparse
from importlib import import_module
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ALERTS = {
    "site-down": ("app.services.telegram.telegram_alert", "send_site_down_alert", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_IDS"),
    "incwo-site-down": ("app.services.telegram.telegram_inc_wo_alert", "send_inc_wo_site_down_alert", "TELEGRAM_BOT_INC_WO_TOKEN", "TELEGRAM_CHAT_IDS_INC_WO"),
    "incwo-power": ("app.services.telegram.telegram_inc_wo_power_alert", "send_inc_wo_category_power_alert", "TELEGRAM_BOT_INC_WO_POWER_TOKEN", "TELEGRAM_CHAT_IDS_INC_WO_POWER"),
    "incwo-general": ("app.services.telegram.telegram_inc_wo_general_alert", "send_inc_wo_general_alert", "TELEGRAM_BOT_INC_WO_GENERAL_TOKEN", "TELEGRAM_CHAT_IDS_INC_WO_GENERAL"),
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=ALERTS)
    parser.add_argument("--dry-run", action="store_true", help="Check only; do not send messages.")
    args = parser.parse_args(argv)
    from flask import Flask
    from app.config import Config
    module_name, function_name, token_key, chat_key = ALERTS[args.kind]
    sender = getattr(import_module(module_name), function_name)
    app = Flask("manual-telegram-test", instance_path=str(ROOT / "instance"))
    app.config.from_object(Config)
    cache_exists = (ROOT / "instance" / "localstorage.db").is_file()
    if args.dry_run:
        print(f"kind={args.kind}; runner=OK; cache_present={cache_exists}")
        print(f"{token_key}: configured={bool(app.config.get(token_key))}")
        print(f"{chat_key}: configured={bool(app.config.get(chat_key))}")
        print("Dry run complete. No alerts sent; no schedulers started.")
        return 0
    if not cache_exists:
        print("Local cache is missing. Start the dashboard and let its first sync finish, then retry.")
        return 1
    try:
        with app.app_context():
            result = sender()
    except (EnvironmentError, RuntimeError) as exc:
        print(f"Telegram test failed: {exc}")
        return 1
    print(f"sent={result['sent']} count={result['count']}")
    return 0 if result["sent"] or result["count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
