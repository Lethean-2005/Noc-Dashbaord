"""Shared alarm-category keyword rules — used by both
app/services/vip/vip_alarm_service.py and
app/services/mentor/mentor_site_service.py to categorize a raw ape_alarm
row (event_name/additional_info) into a human badge category, since both
read the same underlying alarm shape and used to duplicate this list.
"""

# Same NE/connectivity event types ape_alarm.sql originally filtered on —
# any of these means the site itself is unreachable, not just one
# subsystem alarming. Matched as an EXACT (not substring) match against the
# lowercased event_name.
SITE_DOWN_EVENTS = {
    "nodeb is out of service",
    "enodeb is out of service",
    "csl fault",
    "ne is disconnected",
    "ne3sws agent not responding to requests",
    "the link between the server and the me is broken",
    "bts o&m link failure",
    "site abis control link broken",
    "gnodeb out of service",
    "gnodeb du out-of-service",
    "enodeb out of service",
    "nodeb out of service",
    "wcdma base station out of use",
}

# Which radio generation each SITE_DOWN_EVENTS member affects — given
# directly by the user, not inferred. "SRAN" (Single RAN, the shared
# baseband serving every generation at a site) is its own category, not a
# catch-all — used by
# app/services/alarm_site_down/alarm_completely_site_down_service.py to
# know whether an alarm affects one specific technology or all of them.
_SRAN_EVENTS = {
    "ne is disconnected",
    "ne3sws agent not responding to requests",
    "the link between the server and the me is broken",
}
_5G_EVENTS = {"gnodeb out of service", "gnodeb du out-of-service"}
_4G_EVENTS = {"enodeb out of service", "enodeb is out of service"}
_3G_EVENTS = {"nodeb out of service", "nodeb is out of service", "wcdma base station out of use"}
_2G_EVENTS = {"csl fault", "bts o&m link failure", "site abis control link broken"}


def site_down_technology(event_name):
    """ "SRAN"/"5G"/"4G"/"3G"/"2G" for a SITE_DOWN_EVENTS member, or "" for
    anything else (not a Site-Down event, or an unmapped one)."""
    name = (event_name or "").strip().lower()
    if name in _SRAN_EVENTS:
        return "SRAN"
    if name in _5G_EVENTS:
        return "5G"
    if name in _4G_EVENTS:
        return "4G"
    if name in _3G_EVENTS:
        return "3G"
    if name in _2G_EVENTS:
        return "2G"
    return ""


_TECH_DISPLAY_TO_INVENTORY = {"5G": "5g", "4G": "4g", "3G": "3g", "2G": "2g"}


def classify_site_technology_coverage(alarm_rows, inventory_by_site):
    """Splits sites with at least one open Site-Down alarm into two sets —
    (completely_down, partially_down) — by comparing which technologies are
    down against each site's known inventory (site_code -> set of
    2g/3g/4g/5g, from site_technology_cache). Shared by
    app/services/alarm_site_down/alarm_completely_site_down_service.py
    ("Alarm Completely Site Down") and app/services/ran/ran_site_down_service.py
    /ran_tech_down_service.py ("RAN Site Down"/"RAN Tech Down" — the same
    "all techs down" vs "one tech down" distinction, just for the RAN
    Status card), so all three read this one definition instead of each
    re-deriving it.

    completely_down: a SRAN alarm is present (the shared baseband — takes
    down every technology, not just one) OR the union of specific-generation
    alarms fully covers the site's inventory.
    partially_down: at least one specific-generation alarm is present but
    it does NOT fully cover the site's inventory, and no SRAN alarm is
    present either.

    A site with no known technology inventory lands in neither set — there
    is nothing to have fully or partially covered."""
    down_techs_by_site = {}
    covers_all_by_site = set()
    for row in alarm_rows:
        code = row.get("site_code")
        if not code:
            continue
        display = site_down_technology(row.get("event_name"))
        if display == "SRAN":
            covers_all_by_site.add(code)
        elif display:
            down_techs_by_site.setdefault(code, set()).add(_TECH_DISPLAY_TO_INVENTORY[display])

    completely_down, partially_down = set(), set()
    for code, site_techs in inventory_by_site.items():
        if not site_techs:
            continue
        down = down_techs_by_site.get(code, set())
        if code in covers_all_by_site or (down and site_techs.issubset(down)):
            completely_down.add(code)
        elif down:
            partially_down.add(code)
    return completely_down, partially_down
