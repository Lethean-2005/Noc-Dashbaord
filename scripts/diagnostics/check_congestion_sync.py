"""One-off diagnostic — run this directly on the VM to find out exactly
why congestion_history_cache has no data, without waiting on an app
restart or digging through log files.

Usage (from the project root):
    python scripts/diagnostics/check_congestion_sync.py

Safe to run anytime — it runs the SAME sync the background scheduler
runs, against the REAL MSSQL database, and writes into the REAL
instance/localstorage.db cache (not a temp/test one). If it succeeds,
the dashboard's Congestion History card will show real data the very
next time you reload the page — you don't have to wait for a restart.
"""

import sys
from pathlib import Path

# Lives 2 levels under the project root (scripts/diagnostics/) — add the
# root to sys.path so `from app import ...` resolves regardless of CWD,
# same bootstrap webhook/common.py already uses for its own scripts.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app import create_app
from app.services.alarm.alarm_sync_service import AlarmSyncService

app = create_app()

with app.app_context():
    print("Config: CONGESTION_HISTORY_WEEKS =", app.config["CONGESTION_HISTORY_WEEKS"])
    print("Running sync_congestion_history() against the real MSSQL database...")
    print()

    service = AlarmSyncService()
    try:
        result = service.sync_congestion_history()
    except Exception as e:
        print("CRASHED with an uncaught exception:")
        print(f"  {type(e).__name__}: {e}")
        raise

    if result is None:
        print("Returned None — check the error line just above this "
              "(logged via app.utils.logger, e.g. 'MSSQL sync failed for "
              "congestion_history_cache' or 'Cache write failed') for the "
              "real reason: MSSQL connection/query failure, or a local "
              "SQLite write failure.")
    else:
        print(f"SUCCESS — synced {result} row(s) into congestion_history_cache.")
        if result == 0:
            print(
                "0 rows means the query ran fine but found no Congestion "
                "(bandwidth/congestion) alarms with DownTime in the last "
                f"{app.config['CONGESTION_HISTORY_WEEKS']} weeks — a real "
                "possibility if Congestion genuinely hasn't fired recently, "
                "not a bug. Try CONGESTION_HISTORY_WEEKS=12 in .env "
                "temporarily to check a wider window if you want to confirm "
                "there's REALLY nothing, or check tct_alarm_cache/the "
                "Congestion live badge for any currently-active ones."
            )
        else:
            print("Reload the dashboard now — the Congestion History card "
                  "should show this data immediately (it reads straight "
                  "from the cache on every page load, no restart needed).")
