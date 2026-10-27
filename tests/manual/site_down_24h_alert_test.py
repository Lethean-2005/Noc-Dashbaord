"""Manually trigger the Site Down 24h Teams down-alert once, for testing.

Sends a REAL Teams card to whatever SITE_DOWN_24H_ALERT_WEBHOOK_URL is
configured in .env, for every currently-active Site Down incident down
longer than SITE_DOWN_24H_ALERT_THRESHOLD_HOURS that hasn't been
down-alerted yet.

Unlike telegram_alert_test.py, check_and_send_down_alerts() DOES have a
duplicate-send guard (the ledger — see SiteDown24hAlertCacheRepository):
running this script twice in a row will NOT send a second real message
for the same incident. It only sends for incidents not yet recorded as
down-alerted, same as the scheduler's own real run would.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app import create_app
from app.services.incident.site_down_24h_alert_service import check_and_send_down_alerts

app = create_app()
with app.app_context():
    sent = check_and_send_down_alerts()
    print(f"sent={sent}")
