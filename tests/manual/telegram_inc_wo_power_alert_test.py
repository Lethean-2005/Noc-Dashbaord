"""Manually trigger the Telegram INC-WO Category Power alert once, for
testing.

Sends a REAL Telegram message (via TELEGRAM_BOT_INC_WO_POWER_TOKEN) to
whatever TELEGRAM_CHAT_IDS_INC_WO_POWER is configured in .env if any
INC-WO Category Power is currently over INC_WO_POWER_ALERT_THRESHOLD_MIN.
That bot must already be a member of the target chat, or Telegram returns
"chat not found" even with a correct token/chat id.

send_inc_wo_category_power_alert() has no built-in duplicate-send
protection — running this script twice in a row will send two separate
real messages if anything is still over threshold on the second run. Same
reasoning as telegram_inc_wo_alert_test.py — the only thing that normally
prevents repeat sends is the scheduler's own interval (see
app/services/telegram/telegram_inc_wo_power_alert.py's start()), which
this script bypasses entirely by calling the function directly.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app import create_app
from app.services.telegram.telegram_inc_wo_power_alert import send_inc_wo_category_power_alert

app = create_app()
with app.app_context():
    result = send_inc_wo_category_power_alert()
    print(f"sent={result['sent']} count={result['count']}")
