"""Manually trigger the Telegram Site Down alert once, for testing.

Sends a REAL Telegram message to whatever TELEGRAM_CHAT_IDS is configured
in .env (currently the -5532478916 group) if any Incident Site Down is
currently over ALERT_THRESHOLD_MIN.

send_site_down_alert() has no built-in duplicate-send protection — running
this script twice in a row will send two separate real messages if
anything is still over threshold on the second run. The only thing that
normally prevents repeat sends is the scheduler's own 4-hour interval (see
app/services/telegram/telegram_alert.py's start()), which this script bypasses
entirely by calling the function directly.
"""
from app import create_app
from app.services.telegram.telegram_alert import send_site_down_alert

app = create_app()
with app.app_context():
    result = send_site_down_alert()
    print(f"sent={result['sent']} count={result['count']}")
