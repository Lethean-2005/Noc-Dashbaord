"""Standalone study script for app/utils/get_processed_site.py's get_processed_site() —
the Python port of PostgreSQL's get_processed_site(site, additional_info)
PL/pgSQL function.

Run directly: python site_code_study.py
No Flask app, no database connection, no .env needed — every example below
uses hand-built `site`/`additional_info` strings and a tiny fake
site_lookup table, so this is safe to run anywhere, anytime, to see exactly
how the 5-step (6, counting the final fallback) priority chain resolves a
Site Code from those two raw alarm columns.

Priority order (first match wins — see app/utils/get_processed_site.py for the
regexes):
  1. `site` starts with 'PLMN-PLMN/MRBTS-' -> extract sran_id -> look it up
     in site_lookup -> return its site_name with the first 2 characters
     dropped (Postgres: SUBSTRING(site_name, 3)).
  2. First 4-digit run in `site` not immediately followed by another digit
     -> return it as-is (no lookup).
  3. First 4-digit run in `site` immediately followed by '7MR' -> return it
     as-is. In practice this almost never fires: whenever "DDDD7MR" appears,
     step 2's plain (\\d{4})(?!\\d) search already matches the *shifted*
     window one digit to the right (the last 3 digits of DDDD plus the '7'
     of '7MR', followed by 'M' which isn't a digit) before step 3 is ever
     reached. That's a quirk of the original SQL (no negative lookbehind on
     step 2), faithfully reproduced here rather than "fixed" — changing it
     would make this port diverge from Postgres's real, current behavior.
  4. 4-digit nodeb_id from `additional_info`'s 'UIubLink=' -> look it up ->
     same site_name[2:] rule as step 1.
  5. 4-digit bts_id from `additional_info`'s 'GBtsEquipment=' -> look it up
     -> same site_name[2:] rule.
  6. Fallback pattern in `additional_info`: 6 letters, 4 digits, 3 letters
     -> return the 4 digits.
  Otherwise "" (Postgres: NULL).
"""

from app.utils.get_processed_site import get_processed_site, index_site_lookup

# A tiny fake site_lookup_mv / site_lookup_cache — just enough rows to
# demonstrate steps 1, 4, and 5 below. Real data comes from
# app/services/site/site_lookup_sync_service.py at runtime.
LOOKUP_ROWS = [
    {"sran_id": 1234, "nodeb_id": None, "bts_id": None, "site_name": "PP5678"},
    {"sran_id": None, "nodeb_id": 5555, "bts_id": None, "site_name": "KD7777"},
    {"sran_id": None, "nodeb_id": None, "bts_id": 6666, "site_name": "SR8888"},
]
BY_SRAN_ID, BY_NODEB_ID, BY_BTS_ID = index_site_lookup(LOOKUP_ROWS)

EXAMPLES = [
    (
        "Step 1 - sran_id lookup via 'PLMN-PLMN/MRBTS-'",
        "PLMN-PLMN/MRBTS-1234/CELL-3",
        "",
    ),
    (
        "Step 1 falls through (lookup miss) -> step 2's raw digits",
        "PLMN-PLMN/MRBTS-9999/CELL-3",
        "",
    ),
    (
        "Step 2 - first 4-digit run in `site`, no lookup needed",
        "eNodeB-1042-Sector1",
        "",
    ),
    (
        "Step 4 - nodeb_id from additional_info's 'UIubLink='",
        "NoDigitsInSiteAtAll",
        "RncModuleId=1,UIubLink=5555,severity=critical",
    ),
    (
        "Step 5 - bts_id from additional_info's 'GBtsEquipment='",
        "NoDigitsInSiteAtAll",
        "BscId=1,GBtsEquipment=6666,severity=major",
    ),
    (
        "Step 6 - fallback 6-letters/4-digits/3-letters pattern",
        "NoDigitsInSiteAtAll",
        "prefix ABCDEF1234GHI suffix",
    ),
    (
        'Nothing matches -> "" (Postgres: NULL)',
        "NoDigitsInSiteAtAll",
        "no recognizable pattern in here",
    ),
]

if __name__ == "__main__":
    for label, site, additional_info in EXAMPLES:
        code = get_processed_site(site, additional_info, BY_SRAN_ID, BY_NODEB_ID, BY_BTS_ID)
        print(
            f"{label}\n  site={site!r}\n  additional_info={additional_info!r}\n  -> Site Code = {code!r}\n"
        )
