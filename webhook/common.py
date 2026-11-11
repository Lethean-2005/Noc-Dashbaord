"""
webhook/common.py — shared Teams / Power-Automate webhook engine
=================================================================
Every alarm type has its own thin module (webhook/<name>.py) that defines an
`AlertSpec` (title, env var, data fetch, columns, report path) and calls
`run_cli(SPEC)`. All the shared logic — the scrolling HTML table, the connector
(MessageCard) card, and the HTTP send — lives here, so every webhook looks
identical and there is one place to change the styling.

Each webhook reads its OWN url from `.env` (spec.env_var). If that variable is
not set, the send is a no-op (returns sent=False) — so you can add the URLs one
at a time as you receive them.

Ported from Autonoc-Dashboard/webhook/common.py, adapted to this project's
Flask-SQLAlchemy services (every fetch() needs an active app context — see
run_cli() and __main__.py) and its own snake_case cache column names.
"""

import argparse
import json
import os
import re
import ssl
import sys
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Callable

import urllib3
from dotenv import load_dotenv

# ── Bootstrap: make the project importable + load .env ────────────────
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

# Default Teams font (Segoe UI). Teams renders cards in its own system font
# anyway, so this keeps the card clean and native.
_FONT = "'Segoe UI',Arial,sans-serif"

# Teams rejects connector cards larger than ~28KB (RequestEntityTooLarge). Keep
# a safety margin — the payload auto-shrinks its row count to stay under this.
_TEAMS_CARD_LIMIT = 24000

# Same Streamline web host every drilldown template in this project already
# hardcodes for its Incident/INC-WO links (see e.g.
# app/templates/drilldown/alarm_site_down.html) — reused here so a card's
# Incident ID / INC-WO ID cells link straight to the same record.
from app.utils.source_urls import source_url


def _esc(text) -> str:
    """Minimal HTML escape for cell text."""
    s = str(text) if text not in (None, "") else "—"
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


_TS_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::\d{2})?")


def _compact(val):
    """Shorten a full timestamp '2026-07-06 13:29:28' -> '07-06 13:29' so the
    cards stay tight (drop year + seconds). Non-timestamp values pass through."""
    m = _TS_RE.match(str(val))
    if m:
        return f"{m.group(2)}-{m.group(3)} {m.group(4)}:{m.group(5)}"
    return val


_FULL_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})(?::(\d{2}))?")


def _full_ts(val):
    """Normalize a timestamp to the full 'YYYY-MM-DD HH:MM:SS' form (drop any
    fractional seconds / timezone tail, pad missing seconds). Non-timestamps
    pass through unchanged."""
    m = _FULL_TS_RE.match(str(val))
    if m:
        return f"{m.group(1)} {m.group(2)}:{m.group(3) or '00'}"
    return val


# Row keys that are a 0/1 / truthy flag — shown as No/Yes (matches the
# dashboard's own incwo.html rendering of `overdue`).
_YESNO_KEYS = {"overdue"}

# Timestamp columns shown in FULL ('2026-07-07 09:18:10') instead of the
# compact 'MM-DD HH:MM' form — created/occurred/down times are kept exact.
_FULL_TS_KEYS = {"wo_created_at", "occurred_at", "down_time"}

# row key -> (numeric-id sibling key, Streamline path) used to turn an
# Incident ID / INC-WO ID cell into a link. This project's services already
# compute the numeric id separately (incident_numeric_id / wo_numeric_id —
# see every drilldown template's own `https://prd-web-mc.../incident/form/
# {{ row.incident_numeric_id }}` link) instead of it being embeddable in the
# display id string, so the link is looked up from a sibling field rather
# than parsed out of the displayed value itself.
_LINK_KEYS = {
    "incident_id": ("incident_numeric_id", "incident"),
    "wo_id": ("wo_numeric_id", "inc_wo"),
}


def _yesno(val):
    return "No" if str(val).strip() in ("", "0", "—", "None", "False") else "Yes"


def _id_link(row, key):
    """Streamline URL for an Incident ID / INC-WO ID cell, or None if not
    linkable (no numeric id on this row, or `key` isn't one of _LINK_KEYS)."""
    spec = _LINK_KEYS.get(key)
    if not spec:
        return None
    numeric_key, path = spec
    num = row.get(numeric_key)
    if not num:
        return None
    return source_url(f"{path}/form/{num}")


# ── Alert specification ──────────────────────────────────────────────


@dataclass
class AlertSpec:
    key: str  # short id, e.g. "eze"
    title: str  # card title, e.g. "EZE Active Alarms"
    env_var: str  # env var holding this webhook's URL
    fetch: Callable  # () -> (rows, total[, extra]) or rows
    columns: list  # [(label, row_key)]; key "_idx" = row number
    report_path: str = ""  # dashboard path for the "View Report" link
    max_rows: int = 40  # cap rows put into the card
    env_fallback: str = ""  # optional secondary env var (compatibility)


def resolve_url(spec: "AlertSpec"):
    """This webhook's URL from .env (spec.env_var, then spec.env_fallback)."""
    return os.getenv(spec.env_var) or (os.getenv(spec.env_fallback) if spec.env_fallback else None)


def _rows_total(result):
    """Normalize a fetch result into (rows, total).
    Accepts (rows, total), (rows, total, extra...) or a bare list."""
    if isinstance(result, tuple):
        rows = result[0] or []
        total = result[1] if len(result) > 1 and isinstance(result[1], int) else len(rows)
        return rows, total
    rows = result or []
    return rows, len(rows)


# ── Card builders ────────────────────────────────────────────────────


def build_html_table(rows, columns, max_rows=40) -> str:
    """
    Clean, scrolling HTML table (light header, black + bold text) — the
    'Current Sites Down' look. Shows ~5 rows, then a vertical scrollbar; wide
    columns push a horizontal scrollbar (white-space:nowrap).
    """
    # Shared styling (font, bold, black, size) lives on the <table> so every
    # cell inherits it — keeping each <th>/<td> tiny so far more rows fit under
    # Teams' ~28KB card limit. Only non-inheritable bits (padding, border,
    # header background) stay per-cell.
    th = "".join(
        f'<th style="padding:5px 9px;border:1px solid #d9d9d9;'
        f'background:#f3f4f6;text-align:left;">{_esc(label)}</th>'
        for label, _ in columns
    )
    body_rows = []
    for i, r in enumerate(rows[:max_rows], 1):
        cells = []
        for _label, key in columns:
            raw = i if key == "_idx" else r.get(key)
            if key in _YESNO_KEYS:
                disp = _yesno(raw)
            elif raw in (None, ""):
                disp = "—"
            elif key in _FULL_TS_KEYS:
                disp = _full_ts(raw)  # full 'YYYY-MM-DD HH:MM:SS'
            else:
                disp = _compact(raw)
            inner = _esc(disp)
            url = _id_link(r, key) if key != "_idx" else None
            if url:
                inner = f'<a href="{url}" style="color:#2563eb;text-decoration:none;">{inner}</a>'
            cells.append(f'<td style="padding:4px 9px;border:1px solid #ededed;">{inner}</td>')
        body_rows.append(f"<tr>{''.join(cells)}</tr>")

    # ~header + 5 data rows, then scroll.
    return (
        '<div style="max-height:195px;border:1px solid #999;overflow:auto;">'
        f'<table style="border-collapse:collapse;white-space:nowrap;width:100%;'
        f"background:#fff;color:#000;font-weight:700;font-family:{_FONT};"
        f'font-size:10.5px;">'
        f"<thead><tr>{th}</tr></thead>"
        f'<tbody style="vertical-align:top;">{"".join(body_rows)}</tbody>'
        "</table></div>"
    )


def build_payload(spec: "AlertSpec", rows, total) -> dict:
    """The payload we POST. Uses the scrolling HTML Message Card (connector
    card) — it renders with a real vertical + horizontal scrollbar and the clean
    black/bold table.

    Fits as many rows as stay safely under Teams' ~28KB card size limit; the
    header still shows the true total and 'View Report Table' links to the
    full list."""
    n = min(len(rows), spec.max_rows)
    card = build_connector_card(spec, rows, total, max_rows=n)
    while n > 1 and len(json.dumps(card).encode("utf-8")) > _TEAMS_CARD_LIMIT:
        n = max(1, int(n * 0.75))
        card = build_connector_card(spec, rows, total, max_rows=n)
    return card


def build_connector_card(spec: "AlertSpec", rows, total, max_rows=None) -> dict:
    """Connector Card (Office 365 'MessageCard') with the scrolling HTML table."""
    max_rows = spec.max_rows if max_rows is None else max_rows
    base = (os.getenv("DASHBOARD_URL") or "").rstrip("/")
    shown = min(total, max_rows, len(rows))
    now = datetime.now(ZoneInfo("Asia/Phnom_Penh")).strftime("%Y-%m-%d %H:%M")

    if rows:
        subtitle = f"{shown} of {total} active · {now}"
        body = {"text": build_html_table(rows, spec.columns, max_rows), "markdown": False}
    else:
        # No active alarms — still post a card that says so.
        subtitle = f"No active alarms · {now}"
        body = {
            "text": f'<div style="padding:10px 4px;font-family:{_FONT};'
            f'font-size:13px;color:#111;font-weight:700;">'
            f"No active {spec.title} right now.</div>",
            "markdown": False,
        }

    sections = [
        {"activityTitle": f"**{spec.title}**", "activitySubtitle": subtitle, "markdown": True},
        body,
    ]
    if base:
        report = f"{base}{spec.report_path}" if spec.report_path else f"{base}/"
        _link = "color:#2563eb;text-decoration:none;font-weight:600;"
        sections.append(
            {
                "text": f'<span style="font-family:{_FONT};font-size:12px;">'
                f'<a href="{report}" style="{_link}">View Report Table</a>'
                f" &nbsp;|&nbsp; "
                f'<a href="{base}/" style="{_link}">View Dashboard</a></span>',
                "markdown": False,
            }
        )

    return {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": f"{spec.title} ({shown} of {total})",
        "themeColor": "D7263D",
        "sections": sections,
    }


# ── Send + CLI ───────────────────────────────────────────────────────

_POOL = None


def _pool() -> "urllib3.PoolManager":
    """A shared urllib3 PoolManager that sends with a stock
    ``ssl.create_default_context()``.

    Why bare urllib3 and not ``requests``: on some corporate VMs a DPI /
    TLS-inspecting firewall RESETS the default TLS ClientHello (it carries the
    ALPN extension + a distinct option/cipher set), so every POST dies with
    'SSL: UNEXPECTED_EOF_WHILE_READING' even though a plain OpenSSL handshake to
    the very same host succeeds. ``requests`` >= 2.32 rebuilds its own urllib3
    TLS context per request, so setting a plain context on a requests adapter is
    overridden and still gets reset — only a bare PoolManager with the plain
    context reliably sends the ClientHello the firewall lets through. Harmless on
    unfiltered networks — it's just the standard secure (verified) context.
    """
    global _POOL
    if _POOL is None:
        _POOL = urllib3.PoolManager(ssl_context=ssl.create_default_context())
    return _POOL


def _post_json(url: str, payload: dict, timeout: int = 30):
    """POST ``payload`` as JSON via the plain-TLS pool. Returns the urllib3
    HTTPResponse (``.status`` int, ``.data`` bytes); raises on network/TLS
    failure."""
    body = json.dumps(payload).encode("utf-8")
    return _pool().request(
        "POST",
        url,
        body=body,
        headers={"Content-Type": "application/json"},
        timeout=urllib3.Timeout(total=timeout),
    )


def _send_empty_enabled() -> bool:
    """Whether to post a card when an alert has no active rows. Default off:
    empty alerts are skipped. Set WEBHOOK_SEND_EMPTY=true in .env to still post
    a 'no active alarms' card."""
    return os.getenv("WEBHOOK_SEND_EMPTY", "false").strip().lower() == "true"


# A connection-level failure's str(exc) embeds the full request URL, which
# for a Teams incoming webhook includes its signature secret (?sig=...) —
# redacted before it ever lands in a returned "reason" string or a log line.
_URL_IN_ERROR_RE = re.compile(r"https?://\S+")


def _redact_url(text: str) -> str:
    return _URL_IN_ERROR_RE.sub("<redacted-url>", text)


def send(spec: "AlertSpec", max_rows=None) -> dict:
    """Fetch this alert's rows and POST the card to its webhook URL. When there
    are 0 rows the send is skipped (sent=False) unless WEBHOOK_SEND_EMPTY=true.
    Returns {'sent': bool, 'count': int, 'status': int|None}. No-op (sent=False)
    when the URL isn't configured or the alert is empty.

    Must be called inside a Flask app context — every spec.fetch() reads a
    local SQLite cache through this project's Flask-SQLAlchemy repositories,
    which need `current_app`. The background scheduler (webhook/__init__.py's
    start()) already runs inside one; __main__.py pushes its own for the CLI.
    """
    if max_rows is not None:
        spec.max_rows = max_rows
    url = resolve_url(spec)
    if not url:
        return {"sent": False, "count": 0, "status": None, "reason": "no URL set"}
    try:
        rows, total = _rows_total(spec.fetch())
    except Exception as exc:
        return {"sent": False, "count": 0, "status": None, "reason": f"fetch error: {exc}"}

    # No active alarms -> skip the send (don't post an empty card) unless
    # explicitly re-enabled via the WEBHOOK_SEND_EMPTY toggle.
    if not rows and not _send_empty_enabled():
        return {"sent": False, "count": 0, "status": None, "reason": "no active rows"}

    payload = build_payload(spec, rows, total)
    try:
        resp = _post_json(url, payload)
        ok = 200 <= resp.status < 300
        return {
            "sent": ok,
            "count": min(total, spec.max_rows),
            "status": resp.status,
            "reason": "sent" if ok else f"HTTP {resp.status}",
        }
    except Exception as exc:
        return {"sent": False, "count": 0, "status": None, "reason": f"POST error: {_redact_url(str(exc))}"}


def run_cli(spec: "AlertSpec") -> int:
    """Standalone entrypoint for `python webhook/<name>.py`. Creates its own
    Flask app + app context (see module docstring on send() above) since this
    runs outside the web server process."""
    parser = argparse.ArgumentParser(description=f"Send '{spec.title}' to Teams")
    parser.add_argument("--max-rows", type=int, default=spec.max_rows)
    parser.add_argument(
        "--dry-run", action="store_true", help="Build and print the payload without sending"
    )
    args = parser.parse_args()
    spec.max_rows = args.max_rows

    from app import create_app

    app = create_app()
    with app.app_context():
        url = resolve_url(spec)
        try:
            rows, total = _rows_total(spec.fetch())
        except Exception as exc:
            print(f"ERROR: could not load '{spec.title}' data: {exc}")
            return 1
        if not rows and not _send_empty_enabled() and not args.dry_run:
            print(
                f"No active '{spec.title}' rows — skipping send "
                f"(set WEBHOOK_SEND_EMPTY=true to post an empty card)."
            )
            return 0

        payload = build_payload(spec, rows, total)
        print(f"Alert       : {spec.title}")
        print(f"Env var     : {spec.env_var}  ({'set' if url else 'NOT set'})")
        print(f"Rows        : {min(total, spec.max_rows)} of {total}")
        if args.dry_run or not url:
            if not url and not args.dry_run:
                print(
                    f"\n{spec.env_var} is not set in .env — nothing sent. "
                    f"(add the webhook URL, or use --dry-run to preview)"
                )
            print("Payload preview (first 400 chars):")
            print(json.dumps(payload)[:400])
            return 0 if args.dry_run else 3

        print(f"Webhook URL : {url[:80]}...")
        try:
            resp = _post_json(url, payload)
            text = resp.data.decode("utf-8", "replace") if resp.data else ""
            ok = 200 <= resp.status < 300
            print(f"HTTP Status : {resp.status}")
            print(text[:1000] if text else "(empty body)")
            print("OK" if ok else "FAILED")
            return 0 if ok else 4
        except Exception as exc:
            print(f"NETWORK ERROR: {exc}")
            return 5
