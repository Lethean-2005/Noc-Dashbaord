"""Python port of PostgreSQL's get_processed_site(site, additional_info)
PL/pgSQL function.

That function used to run once per row inside ape_alarm.sql's SELECT — a
procedural (RBAR) call per row is expensive on Postgres, and made the query
run measurably longer than a plain column read, which increases exposure to
"conflict with recovery" (the longer a query runs against the replica, the
more likely it collides with WAL replay). ape_alarm.sql now selects the raw
`site`/`additional_info` columns only; get_processed_site() below reproduces
the exact same 5-step priority chain locally, using the site_lookup cache
(mirrors site_lookup_mv, see app/services/site/site_lookup_sync_service.py)
for the sran_id/nodeb_id/bts_id lookups the Postgres function did internally.

Step order (must match the original function exactly):
  1. If `site` starts with 'PLMN-PLMN/MRBTS-', extract a 4-digit sran_id and
     look it up in site_lookup -> site_name[2:].
  2. First 4-digit run in `site` not immediately followed by another digit.
  3. First 4-digit run in `site` immediately followed by '7MR'.
  4. Extract a 4-digit nodeb_id from `additional_info` ('UIubLink=...') and
     look it up in site_lookup -> site_name[2:].
  5. Extract a 4-digit bts_id from `additional_info` ('GBtsEquipment=...')
     and look it up in site_lookup -> site_name[2:].
  6. Fallback pattern in `additional_info`: 6 letters, 4 digits, 3 letters.
  Otherwise "" (the original function returns NULL).
"""
import re

_SRAN_ID_RE = re.compile(r"PLMN-PLMN/MRBTS-(\d{4})(?!\d)")
_FOUR_DIGIT_RE = re.compile(r"(\d{4})(?!\d)")
_SEVEN_MR_RE = re.compile(r"(\d{4})(?=7MR)")
_NODEB_ID_RE = re.compile(r"UIubLink=(\d{4})(?!\d)")
_BTS_ID_RE = re.compile(r"GBtsEquipment=(\d{4})(?!\d)")
_FALLBACK_RE = re.compile(r"[A-Za-z]{6}(\d{4})[A-Za-z]{3}")


def index_site_lookup(rows):
    """rows: site_lookup cache rows ({'sran_id', 'nodeb_id', 'bts_id',
    'site_name'}). Returns (by_sran_id, by_nodeb_id, by_bts_id) dicts —
    one row's site_name can appear under all three, same as
    site_lookup_mv's shape."""
    by_sran_id, by_nodeb_id, by_bts_id = {}, {}, {}
    for row in rows:
        site_name = row.get("site_name")
        sran_id = row.get("sran_id")
        nodeb_id = row.get("nodeb_id")
        bts_id = row.get("bts_id")
        if sran_id is not None:
            by_sran_id[int(sran_id)] = site_name
        if nodeb_id is not None:
            by_nodeb_id[int(nodeb_id)] = site_name
        if bts_id is not None:
            by_bts_id[int(bts_id)] = site_name
    return by_sran_id, by_nodeb_id, by_bts_id


def _resolve_via_lookup(match, lookup):
    if not match:
        return None
    site_name = lookup.get(int(match.group(1)))
    if site_name and len(site_name) >= 2:
        return site_name[2:]
    return None


def get_processed_site(site, additional_info, by_sran_id, by_nodeb_id, by_bts_id):
    """Returns the resolved Site Code, or "" if nothing matched (the
    original function returns NULL in that case)."""
    site = site or ""
    additional_info = additional_info or ""

    if site.startswith("PLMN-PLMN/MRBTS-"):
        resolved = _resolve_via_lookup(_SRAN_ID_RE.search(site), by_sran_id)
        if resolved is not None:
            return resolved

    match = _FOUR_DIGIT_RE.search(site)
    if match:
        return match.group(1)

    match = _SEVEN_MR_RE.search(site)
    if match:
        return match.group(1)

    resolved = _resolve_via_lookup(_NODEB_ID_RE.search(additional_info), by_nodeb_id)
    if resolved is not None:
        return resolved

    resolved = _resolve_via_lookup(_BTS_ID_RE.search(additional_info), by_bts_id)
    if resolved is not None:
        return resolved

    match = _FALLBACK_RE.search(additional_info)
    if match:
        return match.group(1)

    return ""
