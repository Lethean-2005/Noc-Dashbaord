"""
Command-line interface for the Microsoft Teams webhook alerts.

Usage:
    python -m webhook list             show every alert and whether its URL is set
    python -m webhook send-all         send every configured alert (the default)
    python -m webhook send   <key>     send a single alert, e.g. `send eze`
    python -m webhook preview <key>    build and print one alert's card, no sending

Each alert reads its own webhook URL from .env; alerts with no URL are skipped,
so you can enable them one at a time. Running `python -m webhook` with no command
sends all configured alerts (kept for backward compatibility).

Every command runs inside a Flask app context (see main() below) — every
alert's fetch() reads a local SQLite cache through this project's
Flask-SQLAlchemy repositories, which need `current_app`.
"""

import argparse
import json
import sys

from webhook import SPECS
from webhook.common import _rows_total, build_payload, resolve_url, send


def _spec_by_key(key: str):
    """Return the AlertSpec with this key, or None if there is no match."""
    return next((spec for spec in SPECS if spec.key == key), None)


def _print_result(spec, result: dict) -> None:
    """Print one 'sent/FAIL key count=… status=…' status line."""
    state = "sent" if result["sent"] else "FAIL"
    print(
        f"{state}  {spec.key:22} count={result['count']} status={result['status']} "
        f"({result.get('reason', '')})"
    )


def _unknown_key(key: str) -> int:
    print(f"Unknown alert '{key}'. Run 'python -m webhook list' to see the keys.")
    return 2


# ── Commands ──────────────────────────────────────────────────────────


def cmd_list(_args) -> int:
    """List every alert with its URL status and env var."""
    print(f"{'KEY':22} {'URL':4} ENV VAR")
    for spec in SPECS:
        url_state = "set" if resolve_url(spec) else "-"
        print(f"{spec.key:22} {url_state:4} {spec.env_var}")
    return 0


def cmd_send_all(_args) -> int:
    """Send every alert that has a webhook URL configured."""
    any_sent = False
    for spec in SPECS:
        if not resolve_url(spec):
            print(f"skip  {spec.key:22} ({spec.env_var} not set)")
            continue
        result = send(spec)
        any_sent = any_sent or result["sent"]
        _print_result(spec, result)
    if not any_sent:
        print("\nNothing sent — no webhook URLs configured (or no active rows).")
    return 0 if any_sent else 1


def cmd_send(args) -> int:
    """Send a single alert by key."""
    spec = _spec_by_key(args.key)
    if not spec:
        return _unknown_key(args.key)
    if not resolve_url(spec):
        print(f"skip  {spec.key} ({spec.env_var} not set in .env)")
        return 1
    result = send(spec)
    _print_result(spec, result)
    return 0 if result["sent"] else 1


def cmd_preview(args) -> int:
    """Build one alert's card and print it — never sends."""
    spec = _spec_by_key(args.key)
    if not spec:
        return _unknown_key(args.key)
    try:
        rows, total = _rows_total(spec.fetch())
    except Exception as exc:
        print(f"ERROR: could not load '{spec.title}' data: {exc}")
        return 1
    payload = build_payload(spec, rows, total)
    print(f"{spec.title}: {min(total, spec.max_rows)} of {total} rows")
    print(json.dumps(payload, indent=2))
    return 0


# ── Parser + entrypoint ───────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m webhook",
        description="Send Microsoft Teams alert cards. Each alert reads its "
        "webhook URL from .env; alerts with no URL are skipped.",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="show all alerts and whether their URL is set").set_defaults(
        func=cmd_list
    )
    sub.add_parser("send-all", help="send every configured alert").set_defaults(func=cmd_send_all)

    p_send = sub.add_parser("send", help="send one alert by key")
    p_send.add_argument("key", help="alert key, e.g. eze (see 'list')")
    p_send.set_defaults(func=cmd_send)

    p_preview = sub.add_parser("preview", help="build and print one alert's card, no send")
    p_preview.add_argument("key", help="alert key, e.g. eze (see 'list')")
    p_preview.set_defaults(func=cmd_preview)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    func = getattr(args, "func", cmd_send_all)  # no subcommand -> send all

    from app import create_app

    app = create_app()
    with app.app_context():
        return func(args)


if __name__ == "__main__":
    sys.exit(main())
