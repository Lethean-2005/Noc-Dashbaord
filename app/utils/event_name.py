"""Shared cleanup for alarm event_name display text.

Real event_name values from ape_alarm are sometimes prefixed with vendor
boilerplate shaped like "CATEGORY NAME:::real alarm name" — e.g.
"BASE STATION EXTERNAL ALARM NOTIFICATION:::Main Failure",
"BASE STATION CONNECTIVITY PROBLEM:::GTP-U Path Failure", "CELL FAULTY:::...".
16 distinct prefixes were found in real production data (all uppercase
words/numbers/&//_- before a "::: " separator) — rather than hardcode each
one, this strips any prefix matching that shape generically, so a 17th
vendor prefix that shows up later is handled automatically too.

This used to be duplicated logic between
app/services/ran/ran_main_ac_alarm_service.py and
app/services/vip/vip_alarm_service.py (both display event_name from data
that ultimately comes from the same ape_alarm cache), so it lives here once.
"""

import re

_NOISY_PREFIX_RE = re.compile(r"^[A-Z0-9 &/_-]+:::")


def clean_event_name(event_name):
    """Strips a leading vendor-boilerplate prefix for display only — never
    use this on the value passed to matching/categorization logic (e.g.
    _is_main_failure(), _categorize()), which must keep checking the full
    raw text so behavior doesn't depend on whether a given alarm happens to
    carry one of these prefixes."""
    event_name = event_name or ""
    return _NOISY_PREFIX_RE.sub("", event_name)
