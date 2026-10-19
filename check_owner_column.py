"""One-off diagnostic — run this directly on the VM to find out exactly
why the ISP POP drilldown's Owner column isn't showing.

Usage (from the project root, same folder as run.py):
    python check_owner_column.py
"""

import sqlite3

conn = sqlite3.connect("instance/localstorage.db")

print("=== Schema check ===")
cols = [r[1] for r in conn.execute("PRAGMA table_info(isp_pop_alarm_cache)").fetchall()]
has_column = "pro_owner" in cols
print("isp_pop_alarm_cache has pro_owner column:", has_column)

if not has_column:
    print()
    print("THIS IS THE PROBLEM — the app hasn't restarted since the pro_owner")
    print("column was added to the shared alarm schema. The table still has")
    print("its OLD columns. Every active-alarm sync since then has likely")
    print("been failing outright with a SQL error (not just a missing")
    print("Owner value) — check your server log for a line like:")
    print('  "Cache write failed for isp_pop_alarm_cache: ... has no column')
    print('   named pro_owner"')
    print()
    print("FIX: fully stop and restart the Flask process. On the very next")
    print("startup, init_cache_db() detects the column mismatch and drops +")
    print("recreates all 5 alarm tables automatically — the next 10-second")
    print("sync cycle refills them immediately with the new column included.")
else:
    print()
    print("Schema is up to date. Checking actual data next...")
    print()
    print("=== Data check ===")
    rows = conn.execute(
        "SELECT pop_name, pro_owner FROM isp_pop_alarm_cache LIMIT 20"
    ).fetchall()
    print(f"Row count in isp_pop_alarm_cache: {len(rows)}")
    if not rows:
        print("No active ISP POP alarms right now — nothing to show an Owner")
        print("for at all (this is normal if there are currently 0 active")
        print("alarms on that card).")
    else:
        for pop_name, pro_owner in rows:
            print(f"  {pop_name!r:30} pro_owner={pro_owner!r}")
        blank_count = sum(1 for _, o in rows if not o)
        if blank_count:
            print()
            print(f"{blank_count}/{len(rows)} row(s) have a BLANK pro_owner.")
            print("This means MSSQL's TBL_POP.PRO_OWNER was NULL/empty for")
            print("that site — a real data gap in the source system, not a")
            print("bug in this app (the template just shows it blank, same")
            print("as the Map page does for an unset owner).")
