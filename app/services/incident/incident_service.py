"""Business logic for the Incident / INC-WO card, plus the "Incident Site
Down" card on the Custom Dashboard (reports/index.html).

Reads local caches (instance/localstorage.db, see app/database/cache.py)
that app/services/incident/incident_scheduler.py keeps in sync with
PostgreSQL in the background.
"""

import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.repositories.incident.incident_closed_trend_cache_repository import (
    IncidentClosedTrendCacheRepository,
)
from app.repositories.incident.incident_created_trend_cache_repository import (
    IncidentCreatedTrendCacheRepository,
)
from app.repositories.incident.incident_site_down_cache_repository import (
    IncidentSiteDownCacheRepository,
)
from app.repositories.incident.incident_site_down_duration_weekly_cache_repository import (
    IncidentSiteDownDurationWeeklyCacheRepository,
)
from app.repositories.incident.incident_site_down_root_cause_cache_repository import (
    IncidentSiteDownRootCauseCacheRepository,
)
from app.repositories.incident.incident_duration_weekly_cache_repository import (
    IncidentDurationWeeklyCacheRepository,
)
from app.repositories.incident.incident_status_cache_repository import IncidentStatusCacheRepository
from app.utils.datetime import elapsed_minutes
from app.utils.ttl_cache import ttl_cache

_STATUS_TABLE = "incident_by_status"
_SITE_DOWN_TABLE = "incident_site_down"
_CLOSED_TREND_TABLE = "incident_closed_trend"
_CREATED_TREND_TABLE = "incident_created_trend"
_SITE_DOWN_DURATION_WEEKLY_TABLE = "incident_site_down_duration_weekly"
_DURATION_WEEKLY_TABLE = "incident_duration_weekly"
_SITE_DOWN_ROOT_CAUSE_TABLE = "incident_site_down_root_cause"

# Geometry for the "Site-Down Duration – Weekly Trend" line chart: same
# 700x180 SVG/plot-area convention as _VOLUME_X_POSITIONS above. X
# positions are computed per-call in get_site_down_duration_trend()
# (evenly spaced across however many buckets `duration_buckets` leaves
# active), not fixed here, since the "Filter by Duration" control can
# narrow the usual 6 down to fewer. <=15m is its own bucket (not folded
# into the next one up) so a flood of very-fast-resolved incidents
# doesn't get lost inside the same bucket as a true multi-hour one.
_DURATION_BUCKET_LABELS = ("≤15m", "16m-4h", "4-8h", "8-12h", "12-24h", ">24h")

# Duration bucket label -> URL-safe token (badge `type`), since "<"/">"
# can't ride in a query string cleanly. Combined with the week's own
# ISO Monday date in get_site_down_duration_trend()'s badge_type (e.g.
# "lt15m_2026-09-08") — see get_site_down_duration_details() for the
# reverse lookup.
_DURATION_BUCKET_TOKENS = {
    "≤15m": "lt15m",
    "16m-4h": "16m_4h",
    "4-8h": "4_8h",
    "8-12h": "8_12h",
    "12-24h": "12_24h",
    ">24h": "gt24h",
}

# Geometry for the "Incident Volume – Week over Week" line chart: a
# 700x180 SVG, 7 evenly spaced x positions (Mon..Sun), y mapped between
# _VOLUME_PLOT_TOP and _VOLUME_PLOT_BOTTOM (0).
_VOLUME_X_POSITIONS = (0.0, 116.7, 233.3, 350.0, 466.7, 583.3, 700.0)
_VOLUME_PLOT_TOP = 40.0
_VOLUME_PLOT_BOTTOM = 170.0
_WEEKDAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# Fixed display order for Incident Volume's Severity filter/breakdowns —
# urgency rank (Critical worst), not alphabetical or "biggest change"
# order. "Warning" is real but negligible (1 incident total, confirmed
# live) and deliberately excluded everywhere this order applies, by
# request.
_SEVERITY_ORDER = ("Critical", "Major", "Minor")

# One color per selected week on the Volume/Closed cards' week-compare
# chart, newest week first — orange stays "the current week" the same
# way it always has, older weeks fall back to indigo/green/amber. Keep
# this the same length as _WEEKS_AVAILABLE below — SLA Compliance's own
# "Compare Weeks" defaults to every available week checked at once (see
# performance_cards.html's own help text), so one color per available
# week is needed or the oldest line would silently reuse color 0
# (idx % len(_SERIES_COLORS) wrapping around) and look like the SAME
# week as the newest one. (A 5th color, #ec4899, was added here
# alongside a since-reverted _WEEKS_AVAILABLE=5 — removed again now
# that it's back to 4, see that constant's own comment for why.)
_SERIES_COLORS = ("#f97316", "#6366f1", "#22c55e", "#eab308")
# This week + 3 prior (28 days of checkboxes). Briefly bumped to 5
# (35 days) after confirming live that a rolling "30-31 day" sync
# window didn't divide evenly into 4 Mon-Sun weeks: checking every
# offered week still left a 2-3 day sliver of the oldest data
# unreachable that "no filter" included anyway (confirmed on Top 10
# Site Down: site 1679 showed 458 unfiltered but only 434 with all 4
# weeks checked). The real fix was the OTHER side of that gap, not
# this number: every sync query this list drives (incident_created_
# trend, incident_closed_trend, incident_duration_weekly,
# incident_site_down_duration_weekly, incident_site_down_root_cause)
# now pulls its own `since` from incident_sync_service.py's
# _oldest_available_monday() — which computes directly off this same
# _WEEKS_AVAILABLE — instead of an independent rolling day count. So
# the sync window and this checkbox list can never drift apart again
# regardless of what this number is set to; back to a clean 4 (a
# calendar month is 28-31 days, never evenly divisible into whole
# weeks, so "4 weeks" was never going to equal "a month" — the window
# is now defined as exactly 4 ISO weeks on both sides, not an
# approximation of a month).
_WEEKS_AVAILABLE = 4

# Category display names this app derives via SQL's own
# INITCAP(REPLACE(incident_category, '_', ' ')) (e.g.
# incident_created_trend_by_ids.sql) — "customer_complaint" becomes
# exactly this string on every category-filterable row dashboard-wide,
# which is what _filter_rows_by_categories() below compares against.
_DEFAULT_EXCLUDED_CATEGORIES = {"Customer Complaint"}


def _filter_rows_by_categories(rows, categories):
    """Narrows `rows` to `categories` if given (a list of exact display
    names, straight from a "Filter by Category" header's own checked
    boxes); otherwise defaults to every category EXCEPT
    _DEFAULT_EXCLUDED_CATEGORIES — by request, every Filter by Category
    control dashboard-wide (Incident Volume, Incidents Closed, Response
    Time, Resolution Time, SLA Compliance) excludes Customer Complaint
    until it's explicitly checked, unlike every OTHER filter elsewhere
    in this app (weeks, sites, duration buckets, ...) where empty/none
    genuinely means "no filter, show everything". Checking Customer
    Complaint explicitly (it'll be inside `categories`) brings it back
    in, same as checking any other category.

    Shared by every one of those 5 cards' own trend/breakdown methods
    AND their drilldowns (both incident_service.py and dashboard.py
    import this one function) specifically so a drilldown opened from
    a card's default view always matches the exact same population the
    card itself showed — never silently wider just because the
    drilldown's own call site forgot to apply the same default."""
    if categories:
        return [r for r in rows if r.get("category") in categories]
    return [r for r in rows if r.get("category") not in _DEFAULT_EXCLUDED_CATEGORIES]

# Geometry for the "Incident Age – Open" donut chart: a 200x200 SVG
# circle (r=70, centered at 100,100), rotated -90deg in CSS so 0deg =
# top, clockwise. Floating labels sit in a separate 260x260 overlay
# (center 130,130, radius 118px) around the same ring.
_DONUT_R = 70
_DONUT_GAP = 2  # px gap between adjacent ring segments
_DONUT_CENTER = 100
_DONUT_OUTER_CENTER = 130
_DONUT_OUTER_R = 118
_DONUT_OUTER_BOX = 260

# badge `type` -> field/value filters to match in incident_by_status
# (already formatted by incident_by_status.sql).
#
# incident_by_status has one row per (incident, site) pair, so
# get_incident_counts() counts DISTINCT incident_id per badge (matching
# Streamline's own count) rather than raw rows.
BADGE_FILTERS = {
    "new": {"incident_status": "New"},
    "new_site_down": {"incident_status": "New", "category": "Site Down"},
    "in_progress": {"incident_status": "In Progress"},
    "in_progress_site_down": {"incident_status": "In Progress", "category": "Site Down"},
    "overdue": {"overdue": "Yes"},
    "overdue_site_down": {"overdue": "Yes", "category": "Site Down"},
}

# "Incident Age – Open" badge `type` -> (min hours, max hours or None).
# Computed from occurred_at at read time, not a field==value match — see
# _matches_age_bucket(). Keep in sync with get_incident_age_buckets().
_AGE_BUCKET_RANGES = {
    "age_lt4": (0, 4),
    "age_4_8": (4, 8),
    "age_8_12": (8, 12),
    "age_12_24": (12, 24),
    "age_gt24": (24, None),
}
# Chart label -> badge `type`, so each bar's count links to its own drilldown.
_AGE_BUCKET_BADGE_TYPES = {
    "<4h": "age_lt4",
    "4-8h": "age_4_8",
    "8-12h": "age_8_12",
    "12-24h": "age_12_24",
    ">24h": "age_gt24",
}

# "Incident Site Down" badge `type` -> site_grade value (already
# INITCAP'd by incident_site_down.sql). "hub" matches any hub type
# (Hub-Router or Hub-MW), not an exact string.
_SITE_GRADE_BADGES = {
    "diamond": "Diamond",
    "gold": "Gold",
    "silver": "Silver",
    "bronze": "Bronze",
}


def _matches(row, filters):
    return all(row.get(key) == value for key, value in filters.items())


def _matches_age_bucket(row, badge_type):
    lo, hi = _AGE_BUCKET_RANGES[badge_type]
    hours = elapsed_minutes(row.get("occurred_at")) / 60
    return hours >= lo and (hi is None or hours < hi)


# Hardcoded rather than read from current_app.config["TIMEZONE"] — this file's
# functions are called from many test call sites that construct IncidentService
# directly without a Flask app context (same reasoning as app/utils/datetime.py's
# _LOCAL_TZ). This app has exactly one deployment/one NOC/one timezone.
_LOCAL_TZ = ZoneInfo("Asia/Phnom_Penh")


def _now_local():
    """Current moment in the app's configured local timezone (Cambodia,
    UTC+7 — same TIMEZONE config to_local_seconds() uses), explicit
    rather than relying on the server's own OS clock happening to be
    set to the same offset. Every "what week/day is it right now"
    decision in this file (_this_monday(), the "flag today's data
    point" check below) goes through this — the timestamps being
    compared against are already Cambodia-local (converted at sync
    time by to_local_seconds()), so the "now" side of the comparison
    needs to be too, or the two sides silently drift apart on any
    server not already clocked to UTC+7 (see the SLA/Response/
    Resolution Time week-bucketing bug this mirrors the fix for —
    that one was in Postgres, computed on raw UTC before Python ever
    saw the rows; this is the equivalent guard on the Python side)."""
    return datetime.now(_LOCAL_TZ)


def _this_monday():
    today = _now_local().date()
    return today - timedelta(days=today.weekday())


def _bucket_weeks(rows, date_field, mondays):
    """Mon-Sun counts by weekday (index 0=Mon..6=Sun) for any number of
    weeks at once, identified by their own Monday — shared by the
    closed/created trend cards, called with 1-4 weeks depending on the
    "Compare Weeks" checkbox filter (see get_incident_volume_trend()/
    get_incident_closed_trend()/_resolve_selected_weeks()). Returns
    {monday: [7 counts]}. Independent per-week membership checks (not
    elif/exclusive) so picking the same week twice still counts
    correctly.

    Compares date strings directly (10-char slice) instead of
    datetime.strptime() — strptime's locale lookup was ~250ms of a
    ~650ms page load across these caches' 12-15k+ rows (30-day cache,
    see incident_created_trend.sql/incident_closed_trend.sql)."""
    indexes = {
        monday: {(monday + timedelta(days=i)).isoformat(): i for i in range(7)}
        for monday in mondays
    }
    counts = {monday: [0] * 7 for monday in mondays}
    for r in rows:
        value = r.get(date_field)
        if not value:
            continue
        date_str = str(value)[:10]
        for monday, index in indexes.items():
            if date_str in index:
                counts[monday][index[date_str]] += 1
    return counts


def _duration_bucket_index(hours):
    """Hours -> index into _DURATION_BUCKET_LABELS (0=<=15m..5=>24h)."""
    if hours <= 0.25:
        return 0
    if hours < 4:
        return 1
    if hours < 8:
        return 2
    if hours < 12:
        return 3
    if hours < 24:
        return 4
    return 5


def _bucket_site_down_duration(rows, mondays):
    """Site Down incident duration (resolved_at - occurred_at) bucketed
    by _DURATION_BUCKET_LABELS, one count-list per selected week —
    which week a row belongs to is its own closed_at's Monday (matches
    incident_site_down_duration_weekly.sql's closed_at-based 30-day
    window), not occurred_at. Returns {monday: [5 counts]}. Rows
    missing any of the 3 timestamps, or with a negative duration (data
    issue — confirmed none in a live 5,548-row sample, but a defensive
    skip costs nothing), are silently excluded.

    Deduped by incident_id — confirmed live that
    incident_site_down_duration_weekly fans out to one row per
    (incident, site) for multi-site incidents (same pattern as
    incident_site_down elsewhere in this app), with every sibling row
    carrying identical occurred_at/resolved_at/closed_at. Without this
    dedup, a multi-site incident got counted once per site instead of
    once, inflating this card's totals above Site-Down Root Cause —
    Breakdown's own (correctly deduped) count for the exact same
    population — confirmed live: 7791 raw rows vs 5929 unique
    incidents across the same 2 weeks."""
    # Cheap 10-char string lookup (same trick as _bucket_weeks above) to
    # find each row's week BEFORE paying for any fromisoformat() calls —
    # with only 1-2 of the cache's ~4 available weeks selected by default,
    # this skips parsing occurred_at/resolved_at entirely for every row
    # outside the selected weeks instead of parsing all 3 timestamps
    # up front and only then discovering the row doesn't matter.
    date_to_monday = {
        (monday + timedelta(days=i)).isoformat(): monday
        for monday in mondays
        for i in range(7)
    }
    counts = {monday: [0] * len(_DURATION_BUCKET_LABELS) for monday in mondays}
    seen_incidents = set()
    for r in rows:
        closed_at = r.get("closed_at")
        if not closed_at:
            continue
        row_monday = date_to_monday.get(str(closed_at)[:10])
        if row_monday is None:
            continue
        incident_id = r.get("incident_id")
        if incident_id:
            if incident_id in seen_incidents:
                continue
            seen_incidents.add(incident_id)
        occurred_at, resolved_at = r.get("occurred_at"), r.get("resolved_at")
        if not (occurred_at and resolved_at):
            continue
        try:
            # fromisoformat (C-implemented) instead of strptime — strptime's
            # locale lookup on every call was the actual bottleneck: ~3s of a
            # dashboard page load across this cache's 7k+ rows.
            occurred_dt = datetime.fromisoformat(str(occurred_at)[:19])
            resolved_dt = datetime.fromisoformat(str(resolved_at)[:19])
        except ValueError:
            continue
        hours = (resolved_dt - occurred_dt).total_seconds() / 3600
        if hours < 0:
            continue
        counts[row_monday][_duration_bucket_index(hours)] += 1
    return counts


def _bucket_duration_by_created_weekday_and_category(rows, mondays):
    """Same duration bucketing as _bucket_site_down_duration(), but keyed
    off occurred_at's own weekday/Monday instead of closed_at's week —
    and per category, not Site Down only — so it lines up with
    get_incident_volume_day_category_breakdowns()'s per-weekday Category
    counts (also occurred/created-date based) rather than the
    "Site-Down Duration – Weekly Trend" card's closed_at grouping.
    Returns counts[weekday_index][monday][category] = [6 counts].

    An incident's duration comes from Resolved At when present, bucketed
    normally. Any incident MISSING Resolved At — whether it's already
    closed via Closed At (confirmed live: ~11% of closed incidents,
    nearly 1 in 5 for Site Down, have Closed At set but Resolved At left
    NULL — closed through a workflow path that skips it) or still fully
    open (incident_duration_weekly.sql includes these too, not just
    closed ones) — goes straight into the >24h bucket, no real-duration
    calculation needed: per explicit request, every incident missing
    Resolved At displays there, full stop, rather than only the ones
    whose real duration happens to exceed 24h."""
    date_to_week_slot = {
        (monday + timedelta(days=i)).isoformat(): (monday, i)
        for monday in mondays
        for i in range(7)
    }
    counts = [{monday: {} for monday in mondays} for _ in range(7)]
    for r in rows:
        occurred_at = r.get("occurred_at")
        if not occurred_at:
            continue
        slot = date_to_week_slot.get(str(occurred_at)[:10])
        if slot is None:
            continue
        monday, weekday_index = slot
        resolved_at = r.get("resolved_at")
        if resolved_at:
            try:
                occurred_dt = datetime.fromisoformat(str(occurred_at)[:19])
                resolved_dt = datetime.fromisoformat(str(resolved_at)[:19])
            except ValueError:
                continue
            hours = (resolved_dt - occurred_dt).total_seconds() / 3600
            if hours < 0:
                continue
            bucket_index = _duration_bucket_index(hours)
        else:
            bucket_index = 5
        category = r.get("category") or "Uncategorized"
        day_counts = counts[weekday_index][monday]
        if category not in day_counts:
            day_counts[category] = [0] * len(_DURATION_BUCKET_LABELS)
        day_counts[category][bucket_index] += 1
    return counts


def _available_weeks():
    """The Mon-Sun weeks pickable in the Volume/Closed cards' "Compare
    Weeks" checkbox filter: this week plus the _WEEKS_AVAILABLE - 1
    before it, newest first. Capped at _this_monday() (never a week
    that hasn't happened yet — see MEMORY of that bug). Every sync
    query whose data this list can filter (incident_created_trend,
    incident_closed_trend, incident_duration_weekly,
    incident_site_down_duration_weekly, incident_site_down_root_cause)
    pulls from the exact same oldest Monday this function would compute
    for _WEEKS_AVAILABLE — see incident_sync_service.py's
    _oldest_available_monday() — rather than an approximate day count,
    so every offered week is guaranteed to actually have synced data,
    not just "comfortably" likely to.

    `label` is what the CHART itself uses (legend, tooltip — see
    week_labels in get_incident_volume_trend()/get_incident_closed_trend()):
    "This week"/"Last week" for the 2 most recent weeks, "Week N" for
    anything older — N is the real ISO 8601 week number (date.isocalendar(),
    Mon-Sun weeks, correctly rolling over at year boundaries: the Monday
    of ISO week 1 of a year can fall in late December, and a year's final
    week can be numbered 52 or 53 depending on the year), not just a
    sequential count of how many entries are in this dropdown. `week_number`
    + `range_label` (its full Mon-Sun date span, e.g. "Aug 10–16") are
    dropdown-only — graph_cards.html renders "Week {{ week_number }}
    ({{ range_label }})" for the checkbox text."""
    this_monday = _this_monday()
    weeks = []
    for i in range(_WEEKS_AVAILABLE):
        monday = this_monday - timedelta(days=7 * i)
        end = monday + timedelta(days=6)
        week_number = monday.isocalendar()[1]
        if i == 0:
            label = "This week"
        elif i == 1:
            label = "Last week"
        else:
            label = f"Week {week_number}"
        if monday.month == end.month:
            range_label = f"{monday.strftime('%b')} {monday.day}–{end.day}"
        else:
            range_label = f"{monday.strftime('%b')} {monday.day} – {end.strftime('%b')} {end.day}"
        weeks.append({
            "iso": monday.isoformat(),
            "label": label,
            "week_number": week_number,
            "range_label": range_label,
        })
    return weeks


def _resolve_selected_weeks(selected_isos):
    """Query-string week checkboxes (ISO Monday dates) -> date objects,
    newest first (index 0 gets _SERIES_COLORS[0]). Only accepts values
    that are actually offered by _available_weeks(), so a stale/tampered
    value can't request a week outside the cache window. Falls back to
    the latest two COMPLETE weeks (skipping the current, still-in-
    progress one) when nothing valid was picked — comparing against a
    week that's only a few days old makes every count/delta look
    artificially low or wildly skewed purely because it hasn't
    finished yet, not because anything actually changed. "This week"
    stays pickable by hand via Compare Weeks, it just isn't defaulted
    to anymore."""
    available = {w["iso"] for w in _available_weeks()}
    picked = sorted(
        (iso for iso in (selected_isos or []) if iso in available),
        reverse=True,
    )
    if not picked:
        this_monday = _this_monday()
        return [this_monday - timedelta(days=7), this_monday - timedelta(days=14)]
    return [datetime.fromisoformat(iso).date() for iso in picked]


def _with_deltas(day_series):
    """Adds delta_pct to each entry in one day's per-week series list
    (newest week first, see get_incident_volume_trend()/
    get_incident_closed_trend()): that entry's value vs the very next
    OLDER week's value for the same weekday. None for the oldest
    checked week — no earlier one left to compare against. Capped at
    +/-100 — same reasoning as _weekly_time_pct_delta()'s own cap: a
    small older-week count (e.g. 1) makes the raw percentage blow up
    into the hundreds for a small absolute swing (1 -> 5 is +400%),
    which reads as broken rather than informative; +/-100 keeps every
    delta on one readable scale. Mutates and returns `day_series` in
    place."""
    for i, entry in enumerate(day_series):
        if i + 1 < len(day_series):
            prev_value = day_series[i + 1]["value"]
            if prev_value:
                raw_pct = round((entry["value"] - prev_value) / prev_value * 100)
                entry["delta_pct"] = max(-100, min(100, raw_pct))
            else:
                entry["delta_pct"] = None
        else:
            entry["delta_pct"] = None
    return day_series


def _filter_rows_by_date(rows, date_field, badge_type):
    """Rows for one Volume/Closed-trend day OR week badge. badge_type is
    either "date_YYYY-MM-DD" (see get_incident_volume_trend()/
    get_incident_closed_trend()) — the exact calendar date that day's
    dot/bar represents — or "week_YYYY-MM-DD" (see
    get_incident_volume_category_breakdown()'s own badge_type per week
    cell) — the whole Mon-Sun week starting that Monday, since a "By
    Category" cell is a week total, not a single day's. None if
    badge_type isn't in either form."""
    if badge_type.startswith("date_"):
        date_str = badge_type[len("date_"):]
        return [r for r in rows if str(r.get(date_field) or "")[:10] == date_str]
    if badge_type.startswith("week_"):
        try:
            monday = datetime.fromisoformat(badge_type[len("week_"):]).date()
        except ValueError:
            return None
        date_strs = {(monday + timedelta(days=i)).isoformat() for i in range(7)}
        return [r for r in rows if str(r.get(date_field) or "")[:10] in date_strs]
    return None


def _nice_ticks(max_value, intervals=5):
    """`intervals` evenly-spaced tick values from 0 up to a round number
    above `max_value` (1/2/5/10 x a power of ten)."""
    if max_value <= 0:
        return [0] * (intervals + 1)
    raw_step = max_value / intervals
    magnitude = 10 ** math.floor(math.log10(raw_step))
    residual = raw_step / magnitude
    for candidate in (1, 2, 5, 10):
        if residual <= candidate:
            step = candidate * magnitude
            break
    else:
        step = 10 * magnitude
    return [round(step * i) for i in range(intervals + 1)]


def _smooth_path(points):
    """SVG path `d` string tracing `points` as a Catmull-Rom spline
    (tension 1/6) converted to cubic Bezier — passes exactly through
    every point, unlike a quadratic-midpoint curve that only passes
    near them (visible once dot markers sit at the exact coordinates)."""
    if len(points) < 2:
        return f"M{points[0][0]:.1f},{points[0][1]:.1f}" if points else ""

    d = f"M{points[0][0]:.1f},{points[0][1]:.1f}"
    n = len(points)
    for i in range(n - 1):
        p0 = points[i - 1] if i > 0 else points[i]
        p1 = points[i]
        p2 = points[i + 1]
        p3 = points[i + 2] if i + 2 < n else points[i + 1]
        c1x = p1[0] + (p2[0] - p0[0]) / 6
        c1y = p1[1] + (p2[1] - p0[1]) / 6
        c2x = p2[0] - (p3[0] - p1[0]) / 6
        c2y = p2[1] - (p3[1] - p1[1]) / 6
        d += f" C{c1x:.1f},{c1y:.1f} {c2x:.1f},{c2y:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    return d


def _format_tick(value):
    """1500 -> '1.5K', 200 -> '200'."""
    if value >= 1000:
        return f"{value / 1000:g}K"
    return str(int(value))


def _matches_site_down_badge(row, badge_type):
    """True if `row` belongs under the clicked "Incident Site Down"
    badge (hub/diamond/gold/silver/bronze)."""
    if badge_type == "hub":
        return (row.get("hub_site") or "").strip() not in ("", "Not Hub")
    return row.get("site_grade") == _SITE_GRADE_BADGES.get(badge_type)




class IncidentService:
    def __init__(
        self,
        status_cache_repository=None,
        site_down_cache_repository=None,
        closed_trend_cache_repository=None,
        created_trend_cache_repository=None,
        site_down_duration_weekly_cache_repository=None,
        duration_weekly_cache_repository=None,
        site_down_root_cause_cache_repository=None,
    ):
        self.status_cache_repository = status_cache_repository or IncidentStatusCacheRepository()
        self.site_down_cache_repository = (
            site_down_cache_repository or IncidentSiteDownCacheRepository()
        )
        self.closed_trend_cache_repository = (
            closed_trend_cache_repository or IncidentClosedTrendCacheRepository()
        )
        self.created_trend_cache_repository = (
            created_trend_cache_repository or IncidentCreatedTrendCacheRepository()
        )
        self.site_down_duration_weekly_cache_repository = (
            site_down_duration_weekly_cache_repository or IncidentSiteDownDurationWeeklyCacheRepository()
        )
        self.duration_weekly_cache_repository = (
            duration_weekly_cache_repository or IncidentDurationWeeklyCacheRepository()
        )
        self.site_down_root_cause_cache_repository = (
            site_down_root_cause_cache_repository or IncidentSiteDownRootCauseCacheRepository()
        )
        self._rank_site_down_codes_cache = None

    @ttl_cache(15)
    def get_incident_status_rows(self):
        """Raw incident_by_status rows — fetch once and share via `rows`
        with get_incident_counts()/get_incident_age_buckets() (see
        dashboard.index(), which calls both in the same request) instead
        of each independently re-fetching this table, mirroring
        get_created_trend_rows()."""
        return self.status_cache_repository.fetch_all(_STATUS_TABLE)

    @ttl_cache(15)
    def get_incident_counts(self, rows=None):
        """Badge counts for every Incident-column badge — counts
        DISTINCT incidents (see BADGE_FILTERS), not incident-site rows.
        `rows`, if given (see get_incident_status_rows()), is used
        instead of fetching."""
        rows = rows if rows is not None else self.get_incident_status_rows()
        return {
            badge_type: len({r["incident_id"] for r in rows if _matches(r, filters)})
            for badge_type, filters in BADGE_FILTERS.items()
        }

    def get_incident_age_buckets(self, selected=None, rows=None):
        """Count of currently-open Site Down incidents by age (now -
        occurred_at). Dedupes by incident_id, keeping the earliest
        occurred_at seen. `selected` (a list of bucket labels) narrows
        the returned buckets to just those; empty/None means all 5.
        `rows`, if given (see get_incident_status_rows()), is used
        instead of fetching."""
        rows = rows if rows is not None else self.get_incident_status_rows()
        earliest_by_incident = {}
        for r in rows:
            if r.get("category") != "Site Down":
                continue
            incident_id = r.get("incident_id")
            occurred_at = r.get("occurred_at")
            existing = earliest_by_incident.get(incident_id)
            if existing is None or (occurred_at or "") < (existing or ""):
                earliest_by_incident[incident_id] = occurred_at

        all_labels = ("<4h", "4-8h", "8-12h", "12-24h", ">24h")
        labels = [label for label in all_labels if not selected or label in selected]
        buckets = {label: 0 for label in labels}
        for occurred_at in earliest_by_incident.values():
            hours = elapsed_minutes(occurred_at) / 60
            if hours < 4:
                label = "<4h"
            elif hours < 8:
                label = "4-8h"
            elif hours < 12:
                label = "8-12h"
            elif hours < 24:
                label = "12-24h"
            else:
                label = ">24h"
            if label in buckets:
                buckets[label] += 1
        return buckets

    @ttl_cache(15)
    def get_incident_age_chart(self, selected=None, rows=None):
        """Bar-chart-ready version of get_incident_age_buckets() (Site
        Down incidents only): each bucket's bar_width_pct against the
        shared axis_max, plus donut-ring geometry kept for callers that
        still want it. `selected` passes through to narrow which age
        buckets are included. `rows`, if given (see
        get_incident_status_rows()), passes through too."""
        buckets = self.get_incident_age_buckets(selected, rows=rows)
        total = sum(buckets.values())
        circumference = 2 * math.pi * _DONUT_R

        segments = []
        cum_len = 0.0
        start_angle = 0.0
        for label, count in buckets.items():
            share = (count / total) if total else 0
            sweep_len = share * circumference
            sweep_angle = share * 360
            mid_angle = start_angle + sweep_angle / 2
            rad = math.radians(mid_angle)

            text_x = _DONUT_CENTER + _DONUT_R * math.sin(rad)
            text_y = _DONUT_CENTER - _DONUT_R * math.cos(rad)
            outer_x = _DONUT_OUTER_CENTER + _DONUT_OUTER_R * math.sin(rad)
            outer_y = _DONUT_OUTER_CENTER - _DONUT_OUTER_R * math.cos(rad)

            segments.append({
                "label": label,
                "count": count,
                "badge_type": _AGE_BUCKET_BADGE_TYPES[label],
                "pct": round(share * 100),
                "dasharray": f"{sweep_len:.2f} {max(circumference - sweep_len, 0):.2f}",
                "dashoffset": f"{-cum_len:.2f}",
                "text_x": round(text_x, 1),
                "text_y": round(text_y, 1),
                "outer_left_pct": round(outer_x / _DONUT_OUTER_BOX * 100, 1),
                "outer_top_pct": round(outer_y / _DONUT_OUTER_BOX * 100, 1),
            })
            cum_len += sweep_len + _DONUT_GAP
            start_angle += sweep_angle

        dominant_label, dominant_count = max(
            buckets.items(), key=lambda kv: kv[1], default=("<4h", 0)
        )

        # Bar width is relative to axis_max, not `total` — reads as
        # "how many", comparable across rows, not a stacked share.
        max_count = max(buckets.values(), default=0)
        tick_values = _nice_ticks(max_count)
        axis_max = tick_values[-1] or 1
        for seg in segments:
            seg["bar_width_pct"] = round(seg["count"] / axis_max * 100, 1)

        return {
            "segments": segments,
            "total": total,
            "dominant_label": dominant_label,
            "dominant_pct": round(dominant_count / total * 100) if total else 0,
            "axis_max": axis_max,
            "tick_labels": [_format_tick(v) for v in tick_values],
        }

    @ttl_cache(15)
    def get_available_weeks(self):
        """Weeks pickable in the "Compare Weeks" checkbox filter (see
        _available_weeks()) — for the Volume/Closed cards' header
        dropdown."""
        return _available_weeks()

    @ttl_cache(15)
    def get_closed_trend_rows(self):
        """Raw incident_closed_trend rows (~100ms — 12k+ rows, see
        BaseCacheRepository.fetch_all()) — fetch once and pass into both
        get_incident_closed_trend() and get_closed_trend_categories() via
        their `rows` param (see _graph_cards_context() in
        app/routes/dashboard.py) instead of each fetching it separately."""
        return self.closed_trend_cache_repository.fetch_all(_CLOSED_TREND_TABLE)

    def get_incident_closed_trend(self, categories=None, weeks=None, rows=None):
        """Count of incidents closed by weekday (Mon-Sun), one series
        per selected week, for the "Incidents Closed – Week over Week"
        card. Reads incident_closed_trend, already one row per closed
        incident — no further dedup needed. `categories` (a list)
        narrows to rows matching any one of them; empty/None means no
        filter. `weeks` (a list of ISO Monday dates from the header's
        checkbox filter) picks which weeks to compare; invalid/empty
        falls back to [this week, last week] — see
        _resolve_selected_weeks(). Each day's `series` entries also
        carry delta_pct vs the next older week (see _with_deltas()) for
        the hover tooltip. `rows`, if given (see get_closed_trend_rows()),
        is used instead of fetching — this method never mutates rows in
        place, so passing in a shared/cached list is safe."""
        rows = rows if rows is not None else self.get_closed_trend_rows()
        rows = _filter_rows_by_categories(rows, categories)

        mondays = _resolve_selected_weeks(weeks)
        counts = _bucket_weeks(rows, "closed_at", mondays)
        week_labels = {w["iso"]: w["label"] for w in _available_weeks()}

        all_counts = [v for m in mondays for v in counts[m]]
        tick_values = _nice_ticks(max(all_counts, default=0), intervals=3)
        axis_max = tick_values[-1] or 1

        series = []
        for idx, monday in enumerate(mondays):
            values = counts[monday]
            series.append({
                "monday": monday,
                "label": week_labels.get(monday.isoformat(), f"{monday.strftime('%b')} {monday.day}"),
                "color": _SERIES_COLORS[idx % len(_SERIES_COLORS)],
                "values": values,
                "total": sum(values),
            })

        days = []
        for i, label in enumerate(_WEEKDAY_LABELS):
            day_series = []
            for s in series:
                date_for_day = s["monday"] + timedelta(days=i)
                day_series.append({
                    "label": s["label"],
                    "color": s["color"],
                    "value": s["values"][i],
                    "pct": round(s["values"][i] / axis_max * 100, 1),
                    "date_label": f"{date_for_day.strftime('%b')} {date_for_day.day}",
                    "badge_type": f"date_{date_for_day.isoformat()}",
                })
            # Top-of-bar position (100 - height%), averaged across this
            # day's series, so the hover card (see graph_cards.html/
            # graph_cards.css .bar-tooltip-below/-above) anchors near the
            # actual bars instead of always sitting at a fixed height.
            tooltip_anchor_pct = round(
                sum(100 - s["pct"] for s in day_series) / len(day_series), 1
            ) if day_series else 50.0
            days.append({
                "day": label,
                "series": _with_deltas(day_series),
                "tooltip_anchor_pct": tooltip_anchor_pct,
            })

        return {
            "days": days,
            "week_totals": [{"label": s["label"], "color": s["color"], "total": s["total"]} for s in series],
            "tick_labels": [_format_tick(v) for v in reversed(tick_values)],
        }

    @ttl_cache(15)
    def get_created_trend_rows(self):
        """Raw incident_created_trend rows (~100ms — 15k+ rows, see
        BaseCacheRepository.fetch_all()) — fetch once and pass into both
        get_incident_volume_trend() and get_volume_trend_categories() via
        their `rows` param (see _graph_cards_context() in
        app/routes/dashboard.py) instead of each fetching it separately."""
        return self.created_trend_cache_repository.fetch_all(_CREATED_TREND_TABLE)

    def get_incident_volume_trend(self, categories=None, weeks=None, rows=None):
        """Count of incidents created by weekday (Mon-Sun), one line
        series per selected week, plus SVG line-chart geometry, for the
        "Incident Volume – Week over Week" card. Reads
        incident_created_trend (every incident created recently, any
        status) rather than incident_by_status, which would miss one
        already closed. `categories` (a list) narrows to rows matching
        any one of them; empty/None means no filter. `weeks` (a list of
        ISO Monday dates from the header's checkbox filter) picks which
        weeks to compare; invalid/empty falls back to [this week, last
        week] — see _resolve_selected_weeks(). No area fill regardless
        of how many weeks are selected — flat/clean lines only, same as
        the original 2-week chart. Each day's `series` entries also
        carry delta_pct vs the next older week (see _with_deltas()) for
        the hover tooltip. `rows`, if given (see get_created_trend_rows()),
        is used instead of fetching — this method never mutates rows in
        place, so passing in a shared/cached list is safe."""
        rows = rows if rows is not None else self.get_created_trend_rows()
        rows = _filter_rows_by_categories(rows, categories)

        mondays = _resolve_selected_weeks(weeks)
        counts = _bucket_weeks(rows, "created_at", mondays)
        week_labels = {w["iso"]: w["label"] for w in _available_weeks()}

        all_counts = [v for m in mondays for v in counts[m]]
        tick_values = _nice_ticks(max(all_counts, default=0), intervals=3)
        axis_max = tick_values[-1] or 1

        def value_to_y(value):
            return _VOLUME_PLOT_BOTTOM - (value / axis_max) * (
                _VOLUME_PLOT_BOTTOM - _VOLUME_PLOT_TOP
            )

        this_monday = _this_monday()
        today_idx = _now_local().weekday()
        show_today = this_monday in mondays

        series = []
        for idx, monday in enumerate(mondays):
            values = counts[monday]
            y_vals = [value_to_y(v) for v in values]
            points = list(zip(_VOLUME_X_POSITIONS, y_vals))
            series.append({
                "monday": monday,
                "label": week_labels.get(monday.isoformat(), f"{monday.strftime('%b')} {monday.day}"),
                "color": _SERIES_COLORS[idx % len(_SERIES_COLORS)],
                "path": _smooth_path(points),
                "values": values,
                "y": y_vals,
                "total": sum(values),
            })

        days = []
        for i, (label, x) in enumerate(zip(_WEEKDAY_LABELS, _VOLUME_X_POSITIONS)):
            day_series = []
            for s in series:
                # Plain int day-of-month — strftime's %-d/%#d flag isn't
                # portable between Linux and Windows.
                date_for_day = s["monday"] + timedelta(days=i)
                day_series.append({
                    "label": s["label"],
                    "color": s["color"],
                    "value": s["values"][i],
                    "top_pct": round(s["y"][i] / 180 * 100, 1),
                    "date_label": f"{date_for_day.strftime('%b')} {date_for_day.day}",
                    "badge_type": f"date_{date_for_day.isoformat()}",
                })
            # Averaged across this day's series so the hover card (see
            # graph_cards.html/graph_cards.css .volume-tooltip-below/-above)
            # anchors near the actual dots instead of always sitting at a
            # fixed height.
            tooltip_anchor_pct = round(
                sum(s["top_pct"] for s in day_series) / len(day_series), 1
            ) if day_series else 50.0
            days.append({
                "day": label,
                "x": x,
                "left_pct": round(x / 700 * 100, 1),
                "is_today": show_today and i == today_idx,
                "series": _with_deltas(day_series),
                "tooltip_anchor_pct": tooltip_anchor_pct,
            })

        return {
            "series": series,
            "days": days,
            "grid_x": _VOLUME_X_POSITIONS,
            "week_totals": [{"label": s["label"], "color": s["color"], "total": s["total"]} for s in series],
            "tick_labels": [_format_tick(v) for v in reversed(tick_values)],
        }

    def _incident_volume_field_breakdown(
        self, field, value_key, items_key, categories=None, weeks=None, rows=None,
        sort_by="delta", default_label="Unknown",
    ):
        """Shared implementation behind get_incident_volume_category_breakdown()/
        get_incident_volume_severity_breakdown()/
        get_incident_volume_province_breakdown()/
        get_incident_volume_vendor_breakdown() — same per-week grouping
        and delta math, just grouped by a different row field (`field`)
        for each popup. `value_key`/`items_key` name the grouped
        value/outer list in the returned dict (e.g. "category"/
        "categories") so each caller's existing template markup
        (`row.category`, `volume_category_breakdown.categories`, etc.)
        doesn't need to change just because this got generalized.

        `sort_by`: "delta" (default — the value driving the biggest
        week-over-week increase sits on top, matching Category's own
        "what's driving the change" framing) or "newest_count"
        (Province's own "sort by top incident" ask — ranks by the
        newest selected week's count alone, so the leftmost/current
        column reads top-to-bottom in strictly descending order; ranking
        by a SUM across weeks instead was tried and rejected — it
        breaks that visual ordering (e.g. a province at 293 sorting
        below one at 203 purely because its older week was small),
        which reads as a bug even though the sum itself was correct)."""
        rows = rows if rows is not None else self.get_created_trend_rows()
        rows = _filter_rows_by_categories(rows, categories)

        mondays = _resolve_selected_weeks(weeks)
        week_labels = {w["iso"]: w["label"] for w in _available_weeks()}

        date_to_monday = {
            (monday + timedelta(days=i)).isoformat(): monday
            for monday in mondays
            for i in range(7)
        }
        counts_by_week_value = {monday: {} for monday in mondays}
        for r in rows:
            created_at = r.get("created_at")
            if not created_at:
                continue
            monday = date_to_monday.get(str(created_at)[:10])
            if monday is None:
                continue
            value = r.get(field) or default_label
            counts_by_week_value[monday][value] = counts_by_week_value[monday].get(value, 0) + 1

        if field == "severity":
            # Fixed urgency order (Critical/Major/Minor), Warning
            # excluded — by request, overrides the usual "what's
            # driving the change" delta-sort below for this field only.
            present = {v for counts in counts_by_week_value.values() for v in counts}
            all_values = [v for v in _SEVERITY_ORDER if v in present]
        else:
            all_values = sorted({v for counts in counts_by_week_value.values() for v in counts})
        newest, oldest = (mondays[0], mondays[-1]) if mondays else (None, None)

        breakdown = []
        for value in all_values:
            newest_count = counts_by_week_value[newest].get(value, 0) if newest else 0
            oldest_count = counts_by_week_value[oldest].get(value, 0) if oldest else 0
            week_counts = [counts_by_week_value[m].get(value, 0) for m in mondays]
            breakdown.append({
                value_key: value,
                "weeks": [
                    {
                        "label": week_labels.get(m.isoformat(), f"{m.strftime('%b')} {m.day}"),
                        "count": week_counts[i],
                        "badge_type": f"week_{m.isoformat()}",
                        # vs the very next OLDER week in this same list (mondays is
                        # newest-first) — None for the oldest one shown, same "no
                        # earlier week to compare against" rule as _with_deltas()
                        # on the chart's own hover tooltip. A small "+N"/"-N" right
                        # next to each number, not the one big newest-vs-oldest
                        # `delta` below which only tells you the net over the
                        # whole span.
                        "step_delta": (week_counts[i] - week_counts[i + 1]) if i + 1 < len(week_counts) else None,
                    }
                    for i, m in enumerate(mondays)
                ],
                "delta": newest_count - oldest_count,
                "newest_count": newest_count,
            })
        if field == "severity":
            pass  # already in fixed Critical/Major/Minor order from all_values above
        elif sort_by == "newest_count":
            breakdown.sort(key=lambda b: b["newest_count"], reverse=True)
        else:
            breakdown.sort(key=lambda b: b["delta"], reverse=True)

        return {
            "week_labels": [
                week_labels.get(m.isoformat(), f"{m.strftime('%b')} {m.day}") for m in mondays
            ],
            items_key: breakdown,
        }

    _VOLUME_FIELD_CONFIGS = (
        # (field, value_key, items_key, sort_by, default_label) — same 5
        # values each get_incident_volume_*_breakdown() wrapper already
        # passes to _incident_volume_field_breakdown() individually.
        ("category", "category", "categories", "delta", "Uncategorized"),
        ("severity", "severity", "severities", "delta", "Unknown"),
        ("province", "province", "provinces", "newest_count", "Unknown"),
        ("vendor", "vendor", "vendors", "delta", "Unknown"),
    )

    def _incident_volume_multi_field_breakdown(self, categories=None, weeks=None, rows=None):
        """Category/Severity/Province/Vendor's weekly breakdowns, all 4 at
        once — same output as calling get_incident_volume_category_breakdown()/
        _severity_breakdown()/_province_breakdown()/_vendor_breakdown()
        separately (each field's own sort/default-label/severity-order
        rule is untouched, copied verbatim from
        _incident_volume_field_breakdown() below), just built from ONE
        pass over `rows` instead of 4 separate passes over the same
        ~15k+ rows — confirmed live this was the single biggest chunk of
        a cold dashboard reload. Returns {"categories": {...}, "severities":
        {...}, "provinces": {...}, "vendors": {...}} keyed by each
        config's own items_key, matching what _graph_cards_context()
        already names its own template variables after.

        Only used by _graph_cards_context(), which is the one caller
        that ever needs all 4 simultaneously — every other caller (and
        every existing test) still goes through the original
        one-field-at-a-time methods below, untouched."""
        rows = rows if rows is not None else self.get_created_trend_rows()
        rows = _filter_rows_by_categories(rows, categories)

        mondays = _resolve_selected_weeks(weeks)
        week_labels = {w["iso"]: w["label"] for w in _available_weeks()}
        date_to_monday = {
            (monday + timedelta(days=i)).isoformat(): monday
            for monday in mondays
            for i in range(7)
        }

        # counts_by_field[field][monday][value] = count — every field
        # counted from the SAME row in the SAME pass, instead of
        # re-scanning rows once per field.
        counts_by_field = {
            field: {monday: {} for monday in mondays} for field, *_ in self._VOLUME_FIELD_CONFIGS
        }
        for r in rows:
            created_at = r.get("created_at")
            if not created_at:
                continue
            monday = date_to_monday.get(str(created_at)[:10])
            if monday is None:
                continue
            for field, _value_key, _items_key, _sort_by, default_label in self._VOLUME_FIELD_CONFIGS:
                value = r.get(field) or default_label
                day_counts = counts_by_field[field][monday]
                day_counts[value] = day_counts.get(value, 0) + 1

        newest, oldest = (mondays[0], mondays[-1]) if mondays else (None, None)
        week_labels_out = [
            week_labels.get(m.isoformat(), f"{m.strftime('%b')} {m.day}") for m in mondays
        ]

        result = {}
        for field, value_key, items_key, sort_by, _default_label in self._VOLUME_FIELD_CONFIGS:
            counts_by_week_value = counts_by_field[field]
            if field == "severity":
                present = {v for counts in counts_by_week_value.values() for v in counts}
                all_values = [v for v in _SEVERITY_ORDER if v in present]
            else:
                all_values = sorted({v for counts in counts_by_week_value.values() for v in counts})

            breakdown = []
            for value in all_values:
                newest_count = counts_by_week_value[newest].get(value, 0) if newest else 0
                oldest_count = counts_by_week_value[oldest].get(value, 0) if oldest else 0
                week_counts = [counts_by_week_value[m].get(value, 0) for m in mondays]
                breakdown.append({
                    value_key: value,
                    "weeks": [
                        {
                            "label": week_labels_out[i],
                            "count": week_counts[i],
                            "badge_type": f"week_{m.isoformat()}",
                            "step_delta": (week_counts[i] - week_counts[i + 1]) if i + 1 < len(week_counts) else None,
                        }
                        for i, m in enumerate(mondays)
                    ],
                    "delta": newest_count - oldest_count,
                    "newest_count": newest_count,
                })
            if field == "severity":
                pass
            elif sort_by == "newest_count":
                breakdown.sort(key=lambda b: b["newest_count"], reverse=True)
            else:
                breakdown.sort(key=lambda b: b["delta"], reverse=True)

            result[items_key] = {"week_labels": week_labels_out, items_key: breakdown}
        return result

    def get_incident_volume_category_breakdown(self, categories=None, weeks=None, rows=None):
        """Per-category totals for each active week — the "Incident
        Volume" card's "By Category" popup, next to its week totals
        legend. Answers "this week is up X%, which category is driving
        it": a whole week's count per category, not a single day's (too
        sparse/noisy to read anything into). Same `categories`/`weeks`/
        `rows` params as get_incident_volume_trend(), so the popup
        reflects whatever's currently filtered on the chart itself.
        Sorted by newest active week's count minus oldest active week's
        count, descending — the category driving the increase the most
        sits on top, the one dropping the most sits at the bottom."""
        return self._incident_volume_field_breakdown(
            "category", "category", "categories",
            categories=categories, weeks=weeks, rows=rows, default_label="Uncategorized",
        )

    def get_incident_volume_severity_breakdown(self, categories=None, weeks=None, rows=None):
        """Per-severity (minor/major/critical) totals for each active
        week — the "Incident Volume" card's "By Severity" popup. Same
        shape/sort ("what's driving the change") as
        get_incident_volume_category_breakdown() above, just grouped by
        Streamline's own severity field instead."""
        return self._incident_volume_field_breakdown(
            "severity", "severity", "severities",
            categories=categories, weeks=weeks, rows=rows, default_label="Unknown",
        )

    def get_incident_volume_province_breakdown(self, categories=None, weeks=None, rows=None):
        """Per-province totals for each active week — the "Incident
        Volume" card's "By Province" popup. Sorted by the newest
        selected week's incident count, descending (not by
        week-over-week delta like Category/Severity/Vendor) — "which
        provinces have the most incidents right now" is the useful
        ranking for a place, matching the explicit "sort by top
        incident" ask this popup was built for."""
        return self._incident_volume_field_breakdown(
            "province", "province", "provinces",
            categories=categories, weeks=weeks, rows=rows, sort_by="newest_count", default_label="Unknown",
        )

    def get_incident_volume_vendor_breakdown(self, categories=None, weeks=None, rows=None):
        """Per-vendor totals for each active week — the "Incident
        Volume" card's "By Vendor" popup. `vendor` is resolved at sync
        time (IncidentSyncService._resolve_vendor_name()): mainly from
        mssql_site_onair's own VENDOR column (real NE inventory data,
        same source Map's On-Air sites trust), falling back to the
        site's actual_ran_vendor code (only 3 confirmed-correct codes,
        see app/utils/nms.py) for sites not in that table. "Unknown"
        means neither source has a match for that incident's site."""
        return self._incident_volume_field_breakdown(
            "vendor", "vendor", "vendors",
            categories=categories, weeks=weeks, rows=rows, default_label="Unknown",
        )

    def _incident_volume_day_field_breakdowns(
        self, field, value_key, items_key, categories=None, weeks=None, rows=None,
        default_label="Unknown", include_durations=False,
    ):
        """Shared implementation behind get_incident_volume_day_category_breakdowns()/
        get_incident_volume_day_severity_breakdowns()/
        get_incident_volume_day_province_breakdowns()/
        get_incident_volume_day_vendor_breakdowns() — per-`field` counts
        for ONE weekday at a time (e.g. "Monday this week vs Monday last
        week, which category/severity/province/vendor"), for all 7
        weekdays at once — the x-axis label under the "Incident Volume"
        chart opens the matching one of these, with a tab per field to
        switch which grouping that day's popup shows. Same `delta`/sort
        convention as _incident_volume_field_breakdown() above (newest
        active week's count minus oldest, biggest riser on top) — just
        scoped to this one weekday's counts instead of a whole week's.
        One pass over `rows` builds all 7 days at once rather than
        calling this 7 times over the same rows.

        `include_durations` (only True for the category variant) adds a
        "durations" list (≤15m..>24h, same shape as "weeks") sourced
        from incident_duration_weekly — that table is keyed by category
        alone, so there's no equivalent per-severity/province/vendor
        duration breakdown to attach. Those counts are closed-incidents-
        only (see _bucket_duration_by_created_weekday_and_category()'s
        docstring) so they can legitimately be lower than that row's own
        "weeks" total — an incident still open has no resolved_at yet."""
        rows = rows if rows is not None else self.get_created_trend_rows()
        rows = _filter_rows_by_categories(rows, categories)

        mondays = _resolve_selected_weeks(weeks)
        week_labels = {w["iso"]: w["label"] for w in _available_weeks()}
        if include_durations:
            duration_counts = _bucket_duration_by_created_weekday_and_category(
                self._duration_weekly_rows(), mondays
            )
            zero_duration_counts = [0] * len(_DURATION_BUCKET_LABELS)

        # {date_iso: (monday, weekday_index)}
        date_to_week_slot = {
            (monday + timedelta(days=i)).isoformat(): (monday, i)
            for monday in mondays
            for i in range(7)
        }
        # counts[weekday_index][monday][value] = count
        counts = [{monday: {} for monday in mondays} for _ in range(7)]
        for r in rows:
            created_at = r.get("created_at")
            if not created_at:
                continue
            slot = date_to_week_slot.get(str(created_at)[:10])
            if slot is None:
                continue
            monday, weekday_index = slot
            value = r.get(field) or default_label
            day_counts = counts[weekday_index][monday]
            day_counts[value] = day_counts.get(value, 0) + 1

        results = []
        for weekday_index, label in enumerate(_WEEKDAY_LABELS):
            counts_by_week_value = counts[weekday_index]
            if field == "severity":
                present = {v for wk in counts_by_week_value.values() for v in wk}
                all_values = [v for v in _SEVERITY_ORDER if v in present]
            else:
                all_values = sorted({v for wk in counts_by_week_value.values() for v in wk})
            newest, oldest = (mondays[0], mondays[-1]) if mondays else (None, None)
            if include_durations:
                duration_counts_by_week = duration_counts[weekday_index]
            items_out = []
            for value in all_values:
                week_counts = [counts_by_week_value[m].get(value, 0) for m in mondays]
                item_out = {
                    value_key: value,
                    "weeks": [
                        {
                            "label": week_labels.get(m.isoformat(), f"{m.strftime('%b')} {m.day}"),
                            "count": week_counts[i],
                            "badge_type": f"date_{(m + timedelta(days=weekday_index)).isoformat()}",
                            "step_delta": (week_counts[i] - week_counts[i + 1]) if i + 1 < len(week_counts) else None,
                        }
                        for i, m in enumerate(mondays)
                    ],
                    "delta": (
                        (counts_by_week_value[newest].get(value, 0) if newest else 0)
                        - (counts_by_week_value[oldest].get(value, 0) if oldest else 0)
                    ),
                }
                if include_durations:
                    duration_week_counts = [
                        duration_counts_by_week[m].get(value, zero_duration_counts) for m in mondays
                    ]
                    newest_durations = (
                        duration_counts_by_week[newest].get(value, zero_duration_counts) if newest else zero_duration_counts
                    )
                    oldest_durations = (
                        duration_counts_by_week[oldest].get(value, zero_duration_counts) if oldest else zero_duration_counts
                    )
                    item_out["durations"] = [
                        {
                            "label": bucket_label,
                            "weeks": [
                                {
                                    "label": week_labels.get(m.isoformat(), f"{m.strftime('%b')} {m.day}"),
                                    "count": duration_week_counts[i][bucket_index],
                                    "badge_type": f"{_DURATION_BUCKET_TOKENS[bucket_label]}_{m.isoformat()}_{weekday_index}",
                                    "step_delta": (
                                        duration_week_counts[i][bucket_index] - duration_week_counts[i + 1][bucket_index]
                                    ) if i + 1 < len(mondays) else None,
                                }
                                for i, m in enumerate(mondays)
                            ],
                            "delta": newest_durations[bucket_index] - oldest_durations[bucket_index],
                        }
                        for bucket_index, bucket_label in enumerate(_DURATION_BUCKET_LABELS)
                    ]
                items_out.append(item_out)
            if field != "severity":
                items_out.sort(key=lambda c: c["delta"], reverse=True)
            results.append({
                "weekday": label,
                "week_labels": [
                    week_labels.get(m.isoformat(), f"{m.strftime('%b')} {m.day}") for m in mondays
                ],
                items_key: items_out,
            })
        return results

    def _incident_volume_multi_field_day_breakdowns(self, categories=None, weeks=None, rows=None):
        """Category/Severity/Province/Vendor's per-weekday breakdowns
        (all 7 weekdays), all 4 fields at once — same output as calling
        get_incident_volume_day_category_breakdowns()/_day_severity_/
        _day_province_/_day_vendor_breakdowns() separately, built from
        ONE pass over `rows` instead of 4. Category's duration
        accordion is unaffected — still one extra call to
        _bucket_duration_by_created_weekday_and_category(), same as
        get_incident_volume_day_category_breakdowns() already does,
        just attached here instead. See
        _incident_volume_multi_field_breakdown()'s own docstring for
        why this exists only for _graph_cards_context()'s benefit —
        every existing test still goes through the untouched
        one-field-at-a-time methods below."""
        rows = rows if rows is not None else self.get_created_trend_rows()
        rows = _filter_rows_by_categories(rows, categories)

        mondays = _resolve_selected_weeks(weeks)
        week_labels = {w["iso"]: w["label"] for w in _available_weeks()}
        duration_counts = _bucket_duration_by_created_weekday_and_category(
            self._duration_weekly_rows(), mondays
        )
        zero_duration_counts = [0] * len(_DURATION_BUCKET_LABELS)

        date_to_week_slot = {
            (monday + timedelta(days=i)).isoformat(): (monday, i)
            for monday in mondays
            for i in range(7)
        }
        # counts_by_field[field][weekday_index][monday][value] = count
        counts_by_field = {
            field: [{monday: {} for monday in mondays} for _ in range(7)]
            for field, *_ in self._VOLUME_FIELD_CONFIGS
        }
        for r in rows:
            created_at = r.get("created_at")
            if not created_at:
                continue
            slot = date_to_week_slot.get(str(created_at)[:10])
            if slot is None:
                continue
            monday, weekday_index = slot
            for field, _value_key, _items_key, _sort_by, default_label in self._VOLUME_FIELD_CONFIGS:
                value = r.get(field) or default_label
                day_counts = counts_by_field[field][weekday_index][monday]
                day_counts[value] = day_counts.get(value, 0) + 1

        newest, oldest = (mondays[0], mondays[-1]) if mondays else (None, None)
        week_labels_out = [
            week_labels.get(m.isoformat(), f"{m.strftime('%b')} {m.day}") for m in mondays
        ]

        result = {items_key: [] for _f, _v, items_key, *_ in self._VOLUME_FIELD_CONFIGS}
        for field, value_key, items_key, _sort_by, _default_label in self._VOLUME_FIELD_CONFIGS:
            include_durations = field == "category"
            for weekday_index, label in enumerate(_WEEKDAY_LABELS):
                counts_by_week_value = counts_by_field[field][weekday_index]
                if field == "severity":
                    present = {v for wk in counts_by_week_value.values() for v in wk}
                    all_values = [v for v in _SEVERITY_ORDER if v in present]
                else:
                    all_values = sorted({v for wk in counts_by_week_value.values() for v in wk})
                if include_durations:
                    duration_counts_by_week = duration_counts[weekday_index]
                items_out = []
                for value in all_values:
                    week_counts = [counts_by_week_value[m].get(value, 0) for m in mondays]
                    item_out = {
                        value_key: value,
                        "weeks": [
                            {
                                "label": week_labels_out[i],
                                "count": week_counts[i],
                                "badge_type": f"date_{(m + timedelta(days=weekday_index)).isoformat()}",
                                "step_delta": (week_counts[i] - week_counts[i + 1]) if i + 1 < len(week_counts) else None,
                            }
                            for i, m in enumerate(mondays)
                        ],
                        "delta": (
                            (counts_by_week_value[newest].get(value, 0) if newest else 0)
                            - (counts_by_week_value[oldest].get(value, 0) if oldest else 0)
                        ),
                    }
                    if include_durations:
                        duration_week_counts = [
                            duration_counts_by_week[m].get(value, zero_duration_counts) for m in mondays
                        ]
                        newest_durations = (
                            duration_counts_by_week[newest].get(value, zero_duration_counts) if newest else zero_duration_counts
                        )
                        oldest_durations = (
                            duration_counts_by_week[oldest].get(value, zero_duration_counts) if oldest else zero_duration_counts
                        )
                        item_out["durations"] = [
                            {
                                "label": bucket_label,
                                "weeks": [
                                    {
                                        "label": week_labels_out[i],
                                        "count": duration_week_counts[i][bucket_index],
                                        "badge_type": f"{_DURATION_BUCKET_TOKENS[bucket_label]}_{m.isoformat()}_{weekday_index}",
                                        "step_delta": (
                                            duration_week_counts[i][bucket_index] - duration_week_counts[i + 1][bucket_index]
                                        ) if i + 1 < len(mondays) else None,
                                    }
                                    for i, m in enumerate(mondays)
                                ],
                                "delta": newest_durations[bucket_index] - oldest_durations[bucket_index],
                            }
                            for bucket_index, bucket_label in enumerate(_DURATION_BUCKET_LABELS)
                        ]
                    items_out.append(item_out)
                if field != "severity":
                    items_out.sort(key=lambda c: c["delta"], reverse=True)
                result[items_key].append({
                    "weekday": label,
                    "week_labels": week_labels_out,
                    items_key: items_out,
                })
        return result

    def get_incident_volume_day_category_breakdowns(self, categories=None, weeks=None, rows=None):
        """Per-category counts for one weekday at a time — see
        _incident_volume_day_field_breakdowns() for the full mechanics.
        Only variant with per-bucket durations attached."""
        return self._incident_volume_day_field_breakdowns(
            "category", "category", "categories", categories=categories, weeks=weeks, rows=rows,
            default_label="Uncategorized", include_durations=True,
        )

    def get_incident_volume_day_severity_breakdowns(self, categories=None, weeks=None, rows=None):
        """Per-severity counts for one weekday at a time — same shape as
        get_incident_volume_day_category_breakdowns() but grouped by
        Streamline's own severity field; no per-bucket duration
        breakdown (see _incident_volume_day_field_breakdowns()'s
        docstring for why)."""
        return self._incident_volume_day_field_breakdowns(
            "severity", "severity", "severities", categories=categories, weeks=weeks, rows=rows,
        )

    def get_incident_volume_day_province_breakdowns(self, categories=None, weeks=None, rows=None):
        """Per-province counts for one weekday at a time — same shape as
        get_incident_volume_day_category_breakdowns() but grouped by
        province."""
        return self._incident_volume_day_field_breakdowns(
            "province", "province", "provinces", categories=categories, weeks=weeks, rows=rows,
        )

    def get_incident_volume_day_vendor_breakdowns(self, categories=None, weeks=None, rows=None):
        """Per-vendor counts for one weekday at a time — same shape as
        get_incident_volume_day_category_breakdowns() but grouped by
        vendor (see get_incident_volume_vendor_breakdown()'s docstring
        for how `vendor` is resolved)."""
        return self._incident_volume_day_field_breakdowns(
            "vendor", "vendor", "vendors", categories=categories, weeks=weeks, rows=rows,
        )

    @ttl_cache(15)
    def _site_down_duration_weekly_rows(self):
        """Shared read behind every Site-Down Duration/Top Site Down
        method below — all 4 were independently calling fetch_all() on
        the same ~7k-row cache table, so a single dashboard load read it
        4 times over. ttl_cache(15) is safe here the same way it already
        is elsewhere in this file: the underlying cache only actually
        changes once per background sync cycle (300s+), and every caller
        only ever reads fields off these rows or copies them into a new
        dict before adding to it — nothing mutates a row in place, so
        sharing one cached list across calls/requests is safe."""
        return self.site_down_duration_weekly_cache_repository.fetch_all(_SITE_DOWN_DURATION_WEEKLY_TABLE)

    @ttl_cache(15)
    def _duration_weekly_rows(self):
        """Same sharing rationale as _site_down_duration_weekly_rows()
        above, for incident_duration_weekly (every category, not just
        Site Down) — backs get_incident_volume_day_category_breakdowns()'s
        per-category durations and get_incident_volume_day_duration_details()."""
        return self.duration_weekly_cache_repository.fetch_all(_DURATION_WEEKLY_TABLE)

    def get_site_down_duration_trend(self, weeks=None, duration_buckets=None):
        """Site Down incident duration (resolved_at - issue_occurred_at)
        bucketed into <4h/4-8h/8-12h/12-24h/>24h, one series per
        selected week — the "Site-Down Duration – Weekly Trend" card.
        Same "Compare Weeks" pattern as get_incident_volume_trend()/
        get_incident_closed_trend() above: `weeks` (a list of ISO
        Monday dates) picks which weeks to compare (up to the 4 —
        about a month — offered by _available_weeks()); invalid/empty
        falls back to [this week, last week] — see
        _resolve_selected_weeks(). `duration_buckets` (a list of bucket
        labels, e.g. ["<4h", "4-8h"]) narrows which buckets are plotted
        — same "empty/None means all" convention as
        get_incident_age_buckets()'s `selected` — x positions are
        re-spaced evenly across however many buckets remain, not fixed
        at 5. Reads incident_site_down_duration_weekly (30-day cache,
        synced by IncidentSyncService.sync_site_down_duration_weekly());
        rows are grouped by which week their closed_at falls in — see
        _bucket_site_down_duration()."""
        rows = self._site_down_duration_weekly_rows()
        mondays = _resolve_selected_weeks(weeks)
        counts = _bucket_site_down_duration(rows, mondays)
        week_labels = {w["iso"]: w["label"] for w in _available_weeks()}

        active_indices = [
            i for i, label in enumerate(_DURATION_BUCKET_LABELS)
            if not duration_buckets or label in duration_buckets
        ]
        active_labels = [_DURATION_BUCKET_LABELS[i] for i in active_indices]
        n = len(active_indices) or 1
        active_x_positions = tuple(round(i * 700 / (n - 1), 1) if n > 1 else 0.0 for i in range(n))

        all_counts = [counts[m][i] for m in mondays for i in active_indices]
        tick_values = _nice_ticks(max(all_counts, default=0), intervals=3)
        axis_max = tick_values[-1] or 1

        def value_to_y(value):
            return _VOLUME_PLOT_BOTTOM - (value / axis_max) * (
                _VOLUME_PLOT_BOTTOM - _VOLUME_PLOT_TOP
            )

        series = []
        for idx, monday in enumerate(mondays):
            values = [counts[monday][i] for i in active_indices]
            y_vals = [value_to_y(v) for v in values]
            points = list(zip(active_x_positions, y_vals))
            series.append({
                "monday": monday,
                "label": week_labels.get(monday.isoformat(), f"{monday.strftime('%b')} {monday.day}"),
                "color": _SERIES_COLORS[idx % len(_SERIES_COLORS)],
                "path": _smooth_path(points),
                "values": values,
                "y": y_vals,
                "total": sum(values),
            })

        buckets = []
        for i, (label, x) in enumerate(zip(active_labels, active_x_positions)):
            bucket_token = _DURATION_BUCKET_TOKENS[label]
            bucket_series = []
            for s in series:
                bucket_series.append({
                    "label": s["label"],
                    "color": s["color"],
                    "value": s["values"][i],
                    "top_pct": round(s["y"][i] / 180 * 100, 1),
                    "badge_type": f"{bucket_token}_{s['monday'].isoformat()}",
                })
            tooltip_anchor_pct = round(
                sum(s["top_pct"] for s in bucket_series) / len(bucket_series), 1
            ) if bucket_series else 50.0
            buckets.append({
                "bucket": label,
                "left_pct": round(x / 700 * 100, 1),
                "series": _with_deltas(bucket_series),
                "tooltip_anchor_pct": tooltip_anchor_pct,
            })

        return {
            "series": series,
            "buckets": buckets,
            "grid_x": active_x_positions,
            "week_totals": [{"label": s["label"], "color": s["color"], "total": s["total"]} for s in series],
            "tick_labels": [_format_tick(v) for v in reversed(tick_values)],
        }

    @staticmethod
    def _filter_site_down_rows_by_weeks(rows, weeks):
        """Narrows `rows` to the UNION of `weeks` (ISO Monday dates) by
        closed_at — shared by get_top_site_down() and the Root Cause
        Breakdown methods below, so "whichever week(s) Top 10 Site Down
        is currently filtered to" is the exact same population all of
        them read from. Multi-select (checkboxes — requested, same
        "pick several, union them" pattern as Congestion History's own
        Filter by Week) — unlike _filter_rows_by_weeks() (the OTHER
        root-cause donut's Compare Weeks), empty/all-invalid `weeks`
        means NO filter (the full 30-day window — "All (30 days)",
        this card's own long-standing default), not a 2-week fallback.
        Returns `(filtered_rows, selected_weeks)` — `selected_weeks` is
        `weeks` narrowed to just the valid ISO dates, in no particular
        order."""
        valid_weeks = {w["iso"] for w in _available_weeks()}
        selected = [w for w in (weeks or []) if w in valid_weeks]
        if not selected:
            return rows, []
        date_strs = {
            (datetime.fromisoformat(iso).date() + timedelta(days=i)).isoformat()
            for iso in selected
            for i in range(7)
        }
        return [r for r in rows if str(r.get("closed_at") or "")[:10] in date_strs], selected

    def _rank_site_down_codes(self, rows):
        """Every site in `rows` ranked by Site Down incident count,
        newest-highest first — the full ranking get_top_site_down()
        caps at [:10] for its own bars, and
        get_site_down_root_cause_breakdown()/get_site_down_root_cause_
        weekly_breakdown() also cap at [:10] to know which site_codes
        "Top 10 Site Down — Overtime" is actually showing, rather than
        summarizing every site in the whole 30-day window (confirmed
        live: 2,132 sites have at least one Site Down incident in 30
        days — nowhere close to the 10 sites the card itself shows, so
        defaulting to "every site" instead of just these 10 was the
        actual cause of the root-cause numbers looking wildly
        unrelated to the card next to them).

        Cached per instance by `rows`' own id() — not @ttl_cache, since
        comparing two ~9k-row lists for equality just to decide a cache
        hit would cost nearly as much as ranking them again; identity
        is an O(1) check and exactly right here, because every caller
        either passes the SAME cached list object
        (_site_down_duration_weekly_rows() is itself @ttl_cache(15)'d)
        or a freshly filtered list unique to its own call — so two
        unrelated inputs can never collide under this key. Confirmed
        via profiling that a single default (no-filter) dashboard load
        called this 3x on the exact same rows list — once each from
        get_top_site_down(), get_site_down_root_cause_breakdown(), and
        get_site_down_root_cause_weekly_breakdown() — ~122ms of the
        page's ~480ms context-build time for 2 entirely redundant
        passes over the same rows."""
        cache = self._rank_site_down_codes_cache
        key = id(rows)
        if cache is not None and cache[0] == key:
            return cache[1]
        counts = {}
        for r in rows:
            site_code = r.get("site_code") or ""
            if not site_code:
                continue
            rank_key = (site_code, r.get("site") or site_code)
            counts[rank_key] = counts.get(rank_key, 0) + 1
        result = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
        self._rank_site_down_codes_cache = (key, result)
        return result

    def get_top_site_down(self, weeks=None):
        """Top 10 sites by Site Down incident count — the "Top 10 Site
        Down — Overtime" card. Reads the same 30-day
        incident_site_down_duration_weekly cache the Duration card
        above uses — already one row per (incident, site), multi-site
        incidents already split — so no new sync job was needed for
        this. `weeks` (a list of ISO Monday dates from
        _available_weeks(), the card's own multi-select "Filter by
        Week" checkboxes) narrows the count to the UNION of those
        Mon-Sun weeks by closed_at; empty/all-invalid falls back to the
        full 30-day window ("All", the default) — see
        _filter_site_down_rows_by_weeks()'s own docstring. `badge_type`
        is just `site_code` (no week encoded into it — the currently
        selected weeks apply to the whole card, not per-bar, so a
        drilldown click reads them straight off the request instead;
        same simplification Congestion History's own multi-select
        Filter by Week made for its badge_type). Each bar also carries
        its own "durations" list (≤15m..>24h) — shown in the bar's own
        plain hover tooltip (requested as a tooltip, not a click popup —
        see performance_cards.html's own data-tooltip for this card),
        appended after the total so e.g. "457 site down incidents ·
        ≤15m 443 · 16m-4h 13" all shows on hover. The count
        badge itself still opens the real drilldown on click, same as
        before this ever had a duration breakdown at all."""
        rows, selected_weeks = self._filter_site_down_rows_by_weeks(
            self._site_down_duration_weekly_rows(), weeks
        )
        all_ranked = self._rank_site_down_codes(rows)
        ranked = all_ranked[:10]
        max_count = ranked[0][1] if ranked else 0
        tick_values = _nice_ticks(max_count)
        axis_max = tick_values[-1] or 1

        rows_by_site = {}
        for r in rows:
            rows_by_site.setdefault(r.get("site_code"), []).append(r)

        bars = []
        for (site_code, site_name), count in ranked:
            bucket_counts = {label: 0 for label in _DURATION_BUCKET_LABELS}
            for r in rows_by_site.get(site_code, []):
                bucket = self._row_duration_bucket(r)
                if bucket:
                    bucket_counts[bucket] += 1
            bars.append({
                "site_code": site_code,
                "site": site_name,
                "count": count,
                "bar_width_pct": round(count / axis_max * 100, 1),
                "badge_type": site_code,
                "durations": [
                    {
                        "label": label,
                        "token": _DURATION_BUCKET_TOKENS[label],
                        "count": bucket_counts[label],
                    }
                    for label in _DURATION_BUCKET_LABELS
                ],
            })

        return {
            "bars": bars,
            "total": sum(count for _key, count in all_ranked),
            "weeks": _available_weeks(),
            "selected_weeks": selected_weeks,
            "tick_labels": [_format_tick(v) for v in tick_values],
        }

    def get_site_down_duration_week_options(self, badge_type):
        """For the drilldown's "Filter by Week" control (a radio-button
        group, not checkboxes — picking a week is single-select) —
        given the badge_type of the bucket+week just clicked (e.g.
        "lt4h_2026-09-08"), re-pairs the same bucket with each of the 4
        available weeks so the drilldown page's radio values are
        ready-to-submit badge_types, without the template needing to
        know badge_type's own encoding. None if badge_type isn't in
        that form."""
        try:
            bucket_token, week_token = badge_type.rsplit("_", 1)
        except (ValueError, AttributeError):
            return None
        token_to_label = {v: k for k, v in _DURATION_BUCKET_TOKENS.items()}
        if bucket_token not in token_to_label:
            return None
        return {
            "bucket_label": token_to_label[bucket_token],
            "options": [
                {
                    "iso": w["iso"],
                    "label": w["label"],
                    "range_label": w["range_label"],
                    "week_number": w["week_number"],
                    "badge_type": f"{bucket_token}_{w['iso']}",
                    "selected": w["iso"] == week_token,
                }
                for w in _available_weeks()
            ],
        }

    def get_site_down_duration_details(self, badge_type=None):
        """Rows behind one dot on the "Site-Down Duration" chart —
        badge_type is "{bucket_token}_{monday_iso}" (e.g.
        "lt4h_2026-09-08", see _DURATION_BUCKET_TOKENS), matching
        get_site_down_duration_trend()'s own badge_type per
        bucket-series entry. None if badge_type isn't in that form.
        Every row if badge_type is empty."""
        rows = self._site_down_duration_weekly_rows()
        if not badge_type:
            return rows

        try:
            bucket_token, week_token = badge_type.rsplit("_", 1)
        except ValueError:
            return None
        token_to_label = {v: k for k, v in _DURATION_BUCKET_TOKENS.items()}
        if bucket_token not in token_to_label:
            return None
        bucket_index = _DURATION_BUCKET_LABELS.index(token_to_label[bucket_token])

        try:
            target_monday = datetime.fromisoformat(week_token).date()
        except ValueError:
            return None

        # Cheap 10-char string match for the week (same "avoid strptime's
        # locale lookup over 12-15k+ rows" reasoning as
        # _bucket_site_down_duration() above) BEFORE the more expensive
        # per-row datetime parse below — narrows to ~1/N of the table
        # (N = distinct weeks in the cache) before anything gets parsed,
        # instead of parsing occurred_at/resolved_at for every row only
        # to then discard most of them on the week check.
        date_strs = {(target_monday + timedelta(days=i)).isoformat() for i in range(7)}

        matched = []
        for r in rows:
            occurred_at, resolved_at, closed_at = r.get("occurred_at"), r.get("resolved_at"), r.get("closed_at")
            if not (occurred_at and resolved_at and closed_at):
                continue
            if str(closed_at)[:10] not in date_strs:
                continue
            try:
                occurred_dt = datetime.fromisoformat(str(occurred_at)[:19])
                resolved_dt = datetime.fromisoformat(str(resolved_at)[:19])
            except ValueError:
                continue
            hours = (resolved_dt - occurred_dt).total_seconds() / 3600
            if hours < 0 or _duration_bucket_index(hours) != bucket_index:
                continue
            row = dict(r)
            total_minutes = round(hours * 60)
            h, m = divmod(total_minutes, 60)
            row["duration_display"] = f"{h}h {m}m" if h else f"{m}m"
            matched.append(row)
        return matched

    def get_incident_volume_day_duration_details(self, badge_type=None, categories=None):
        """Rows behind one duration-bucket cell in the "By Category —
        <Weekday>" popup's breakdown (any category) — badge_type is
        "{bucket_token}_{monday_iso}_{weekday_index}" (e.g.
        "lt15m_2026-09-08_0", see _DURATION_BUCKET_TOKENS and
        get_incident_volume_day_category_breakdowns()); `categories`
        (a list) narrows further to that specific category — every
        category's cells share the same badge_type shape, so this is
        what actually tells two different categories' same-bucket-
        same-day cells apart. Deliberately its own method rather than
        reusing get_site_down_duration_details()'s badge_type shape —
        that one matches on closed_at's week, this one matches
        occurred_at's exact created date, same distinction the popup's
        own "may not match the total above" caveat is about (see
        _bucket_duration_by_created_weekday_and_category()'s docstring).
        None if badge_type isn't in that form."""
        rows = self._duration_weekly_rows()
        rows = _filter_rows_by_categories(rows, categories)
        if not badge_type:
            return rows

        try:
            bucket_token, week_token, weekday_token = badge_type.rsplit("_", 2)
        except ValueError:
            return None
        token_to_label = {v: k for k, v in _DURATION_BUCKET_TOKENS.items()}
        if bucket_token not in token_to_label:
            return None
        bucket_index = _DURATION_BUCKET_LABELS.index(token_to_label[bucket_token])

        try:
            target_monday = datetime.fromisoformat(week_token).date()
            weekday_index = int(weekday_token)
        except ValueError:
            return None
        if not 0 <= weekday_index <= 6:
            return None
        target_date = target_monday + timedelta(days=weekday_index)

        matched = []
        for r in rows:
            occurred_at, resolved_at = r.get("occurred_at"), r.get("resolved_at")
            if not occurred_at:
                continue
            if str(occurred_at)[:10] != target_date.isoformat():
                continue
            row = dict(r)
            if resolved_at:
                try:
                    occurred_dt = datetime.fromisoformat(str(occurred_at)[:19])
                    resolved_dt = datetime.fromisoformat(str(resolved_at)[:19])
                except ValueError:
                    continue
                hours = (resolved_dt - occurred_dt).total_seconds() / 3600
                if hours < 0 or _duration_bucket_index(hours) != bucket_index:
                    continue
                total_minutes = round(hours * 60)
                h, m = divmod(total_minutes, 60)
                row["duration_display"] = f"{h}h {m}m" if h else f"{m}m"
            else:
                # Same "missing Resolved At -> >24h, unconditionally" rule
                # as _bucket_duration_by_created_weekday_and_category() —
                # the counts card already puts these here, so the
                # drilldown must show them here too or the count and the
                # list disagree.
                if bucket_index != 5:
                    continue
                row["duration_display"] = "—"
                row["resolved_at"] = row.get("resolved_at") or ""
                row["closed_at"] = row.get("closed_at") or ""
            matched.append(row)
        return matched

    def get_top_site_down_details(self, badge_type=None, weeks=None, duration_buckets=None):
        """Rows behind one bar on the "Top 10 Site Down — Overtime" card
        — badge_type is just the site_code (e.g. "KC1824"); `weeks`
        (a list of ISO Monday dates) is the card's own currently
        selected "Filter by Week" checkboxes, read separately off the
        request rather than encoded into badge_type — same reasoning as
        get_top_site_down()'s own simplified badge_type. Every row if
        badge_type is empty. Empty/all-invalid `weeks` means the full
        30-day window, matching get_top_site_down()'s own "All" default
        — see _filter_site_down_rows_by_weeks()'s own docstring.

        `duration_buckets` (a list of _DURATION_BUCKET_LABELS strings)
        narrows further to rows matching ANY of those buckets — empty/
        None means no filter, same "empty means all" convention as
        every other checkbox filter here. A row with no computable
        duration (missing occurred_at/resolved_at) never matches a
        bucket, same as it never gets a duration_display either."""
        rows, _selected_weeks = self._filter_site_down_rows_by_weeks(
            self._site_down_duration_weekly_rows(), weeks
        )
        if badge_type:
            rows = [r for r in rows if r.get("site_code") == badge_type]
        if duration_buckets:
            rows = [r for r in rows if self._row_duration_bucket(r) in duration_buckets]

        root_cause_lookup = self._root_cause_lookup()
        return self._with_duration_display_and_root_cause(rows, root_cause_lookup)

    @staticmethod
    def _row_duration_bucket(row):
        """One row's own _DURATION_BUCKET_LABELS value (occurred_at ->
        resolved_at), or None if it has no computable duration yet —
        shared by get_top_site_down_details()'s `duration_buckets`
        filter and anywhere else that needs a single row's bucket
        rather than a whole table bucketed at once (see
        _filter_rows_by_duration_bucket() for the table-wide version)."""
        occurred_at, resolved_at = row.get("occurred_at"), row.get("resolved_at")
        if not (occurred_at and resolved_at):
            return None
        try:
            occurred_dt = datetime.fromisoformat(str(occurred_at)[:19])
            resolved_dt = datetime.fromisoformat(str(resolved_at)[:19])
        except ValueError:
            return None
        hours = (resolved_dt - occurred_dt).total_seconds() / 3600
        if hours < 0:
            return None
        return _DURATION_BUCKET_LABELS[_duration_bucket_index(hours)]

    def _with_duration_display_and_root_cause(self, rows, root_cause_lookup):
        """Copies each row, adding duration_display (occurred_at ->
        resolved_at as "Xh Ym"/"Ym", blank if not yet resolvable/
        resolved before it occurred) and root_cause_category (joined
        Root Cause Category names from `root_cause_lookup`, "None" if
        none assigned yet) — shared by get_top_site_down_details() and
        get_site_down_root_cause_details(), since both drill into the
        same incident_site_down_duration_weekly population, just
        grouped differently (by site vs by root cause)."""
        matched = []
        for r in rows:
            row = dict(r)
            row["duration_display"] = ""
            occurred_at, resolved_at = r.get("occurred_at"), r.get("resolved_at")
            if occurred_at and resolved_at:
                try:
                    occurred_dt = datetime.fromisoformat(str(occurred_at)[:19])
                    resolved_dt = datetime.fromisoformat(str(resolved_at)[:19])
                except ValueError:
                    occurred_dt = resolved_dt = None
                if occurred_dt and resolved_dt:
                    hours = (resolved_dt - occurred_dt).total_seconds() / 3600
                    if hours >= 0:
                        total_minutes = round(hours * 60)
                        h, m = divmod(total_minutes, 60)
                        row["duration_display"] = f"{h}h {m}m" if h else f"{m}m"
            row["root_cause_category"] = ", ".join(
                root_cause_lookup.get(row.get("incident_id"), ["None"])
            )
            matched.append(row)
        return matched

    @ttl_cache(15)
    def _root_cause_lookup(self):
        """incident_id -> list of Root Cause Category names, from
        incident_site_down_root_cause (see that table's own note: a
        small number of incidents carry more than one category, kept as
        separate rows there rather than deduped — joined back together
        here with ", " for display since one incident is one row in
        this drilldown). ttl_cache(15) same as _site_down_duration_
        weekly_rows() — this now gets called up to 4 times in a single
        dashboard load (Root Cause Breakdown's pie+table, Site-Down
        Root Cause — Breakdown's pie+table), each a fresh SELECT * +
        dict-build over ~14k rows with no sharing; measured live: that
        made the whole page ~900ms slower than before these cards
        existed. The underlying table only actually changes once per
        background sync cycle (300s+), so sharing one lookup across a
        single request's 4 callers is safe — same reasoning as every
        other ttl_cache(15) in this file."""
        lookup = {}
        for r in self.site_down_root_cause_cache_repository.fetch_all(_SITE_DOWN_ROOT_CAUSE_TABLE):
            incident_id = r.get("incident_id")
            if not incident_id:
                continue
            lookup.setdefault(incident_id, []).append(r.get("root_cause_category") or "None")
        return lookup

    def get_site_down_root_cause_breakdown(self, site_code=None, weeks=None):
        """Root-cause composition of EXACTLY the sites "Top 10 Site
        Down — Overtime" shows — for the "Root Cause Breakdown" donut
        (dashboard.py's _performance_cards_context()). `site_code`, if
        given (clicking a site's code on Top 10 Site Down), narrows to
        just that one site's own incidents — the whole point being that
        clicking a site cross-filters this card in place rather than
        navigating away from it. Without `site_code`, this is the top
        10 sites COMBINED (_rank_site_down_codes()[:10]) — NOT every
        site in the 30-day window: confirmed live that ~2,132 sites
        have at least one Site Down incident in 30 days, so summarizing
        all of them made this card's numbers look unrelated to the 10
        bars sitting right next to it. `weeks`, if given, narrows the
        population the same way get_top_site_down()'s own `weeks` param
        does, so this always reflects whichever week(s) Top 10 Site
        Down is currently filtered to. Each incident is deduped to one
        count per real category it carries (the rare multi-category
        case — see _root_cause_lookup()'s own docstring). "None" (no
        RCA assigned yet — the incident is still open, or auto-closed
        when its alarm cleared, which never sets one) gets its own "Not
        yet assigned" entry in `categories` alongside the real ones, so
        every slice's `pct` is of the same grand total and they sum to
        100%. `total_no_cause` is still returned separately too, for
        the card's subtitle line."""
        rows, selected_weeks = self._filter_site_down_rows_by_weeks(
            self._site_down_duration_weekly_rows(), weeks
        )
        if site_code:
            rows = [r for r in rows if r.get("site_code") == site_code]
        else:
            top10_codes = {code for (code, _name), _count in self._rank_site_down_codes(rows)[:10]}
            rows = [r for r in rows if r.get("site_code") in top10_codes]
        root_cause_lookup = self._root_cause_lookup()

        counts = {}
        no_cause = 0
        seen_incidents = set()
        for r in rows:
            incident_id = r.get("incident_id")
            if not incident_id or incident_id in seen_incidents:
                continue
            seen_incidents.add(incident_id)
            categories = [c for c in root_cause_lookup.get(incident_id, ["None"]) if c != "None"]
            if not categories:
                no_cause += 1
                continue
            for category in categories:
                counts[category] = counts.get(category, 0) + 1

        ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
        total_with_cause = sum(counts.values())
        total_overall = total_with_cause + no_cause
        categories = [
            {
                "category": category,
                "count": count,
                "pct": round(count / total_overall * 100, 1) if total_overall else 0,
                "note": None,
            }
            for category, count in ranked
        ]
        if no_cause:
            categories.append({
                "category": "Cancelled/AutoClosed",
                "count": no_cause,
                "pct": round(no_cause / total_overall * 100, 1) if total_overall else 0,
                "note": None,
            })
        site_name = next((r.get("site") for r in rows if r.get("site_code") == site_code), site_code) if site_code else None
        week_labels = {w["iso"]: w["label"] for w in _available_weeks()}
        weeks_label = (
            ", ".join(week_labels.get(iso, iso) for iso in selected_weeks)
            if selected_weeks
            else "last 30 days"
        )
        return {
            "categories": categories,
            "total_with_cause": total_with_cause,
            "total_no_cause": no_cause,
            "total_overall": total_overall,
            "site_code": site_code,
            "site_name": site_name,
            "weeks_label": weeks_label,
        }

    def get_site_down_root_cause_details(self, badge_type=None, site_code=None, weeks=None):
        """Rows behind one "Root Cause Breakdown" donut slice —
        badge_type is the exact Root Cause Category name (see
        get_site_down_root_cause_breakdown()), or the literal
        "Cancelled/AutoClosed" for that same slice's own "None" group.
        None if no incident in the 30-day Site Down population carries
        that category (a stale/typo'd badge_type). Every incident WITH
        a real category (i.e. excluding "None") if badge_type is empty,
        mirroring get_top_site_down_details()'s own "empty means every
        row" convention. `site_code`/`weeks`, if given, narrow to just
        that site/those weeks first — matches whatever filters were
        active on the card when the slice was clicked (see
        get_site_down_root_cause_breakdown()'s own params), so clicking
        a slice doesn't suddenly widen back out past whatever's
        currently filtered. Deduped to one row per incident first (the
        same table has one row per (incident, site) for multi-site
        incidents — see incident_site_down_duration_weekly's own
        PRIMARY KEY note in app/database/cache.py), so one incident
        touching several sites doesn't show up more than once here."""
        rows, _selected_weeks = self._filter_site_down_rows_by_weeks(
            self._site_down_duration_weekly_rows(), weeks
        )
        if site_code:
            rows = [r for r in rows if r.get("site_code") == site_code]
        else:
            top10_codes = {code for (code, _name), _count in self._rank_site_down_codes(rows)[:10]}
            rows = [r for r in rows if r.get("site_code") in top10_codes]
        root_cause_lookup = self._root_cause_lookup()

        seen_incidents = set()
        deduped = []
        for r in rows:
            incident_id = r.get("incident_id")
            if not incident_id or incident_id in seen_incidents:
                continue
            seen_incidents.add(incident_id)
            deduped.append(r)

        if badge_type == "Cancelled/AutoClosed":
            deduped = [
                r
                for r in deduped
                if all(c == "None" for c in root_cause_lookup.get(r.get("incident_id"), ["None"]))
            ]
        elif badge_type:
            valid_categories = {
                category
                for categories in root_cause_lookup.values()
                for category in categories
                if category != "None"
            }
            if badge_type not in valid_categories:
                return None
            deduped = [
                r for r in deduped if badge_type in root_cause_lookup.get(r.get("incident_id"), [])
            ]
        else:
            deduped = [
                r
                for r in deduped
                if any(c != "None" for c in root_cause_lookup.get(r.get("incident_id"), ["None"]))
            ]

        return self._with_duration_display_and_root_cause(deduped, root_cause_lookup)

    def get_site_down_root_cause_weekly_breakdown(self, site_code=None, weeks=None):
        """Category x week table for the "Root Cause Breakdown" card's
        table view (a toggle next to its pie chart — the pie only ever
        shows one flat total, this answers "is a category trending up
        or down"). Its own week COLUMNS follow Top 10 Site Down's
        "Filter by Week" selection directly (whichever week(s) are
        checked there), each category's step change between the
        newest and oldest of them — falling back to the last 2
        complete weeks (_available_weeks()[1:3], same "skip index 0,
        the in-progress current week" convention _graph_cards_context()'s
        own `default_weeks` already uses) only when nothing's
        selected ("All"). Confirmed live this HAS to follow the
        selection, not stay fixed: with a single older week picked
        (narrowing the population to just that week's incidents), the
        old fixed "Last week vs Week N" columns matched NONE of that
        population's own occurred_at dates, so the table rendered "No
        incidents" even though the pie right above it showed real
        numbers for the exact same filter. Same incident population as
        get_site_down_root_cause_breakdown() — optionally narrowed to
        one site_code after clicking a site on "Top 10 Site Down —
        Overtime" AND/OR to `weeks` (that card's own "Filter by Week"
        selection — see _filter_site_down_rows_by_weeks()), same
        cross-filter as that method's own params, bucketed by
        occurred_at instead of a single 30-day total.
        "None" (no RCA yet) gets its own "Cancelled/AutoClosed" row here
        too, same as the pie's own matching entry (see
        get_site_down_root_cause_breakdown()'s own docstring for why).
        Each category row also carries its own "durations" list
        (≤15m..>24h, same _DURATION_BUCKET_LABELS/same shape as
        "weeks") — same expand-a-row-to-see-its-duration-breakdown UI
        as the "Incident Volume" card's own per-category popup
        (_volume_day_popup_body.html's .volume-category-row/.volume-
        duration-panel), requested to match that same interaction here.
        Duration comes straight off each row's own occurred_at/
        resolved_at (same fields _with_duration_display_and_root_cause()
        already reads) rather than a second table lookup — unlike
        Incident Volume's own version, which has to join
        incident_duration_weekly separately since ITS rows don't carry
        resolved_at at all."""
        rows, selected_weeks = self._filter_site_down_rows_by_weeks(
            self._site_down_duration_weekly_rows(), weeks
        )
        if site_code:
            rows = [r for r in rows if r.get("site_code") == site_code]
        else:
            top10_codes = {code for (code, _name), _count in self._rank_site_down_codes(rows)[:10]}
            rows = [r for r in rows if r.get("site_code") in top10_codes]
        root_cause_lookup = self._root_cause_lookup()

        seen_incidents = set()
        deduped = []
        for r in rows:
            incident_id = r.get("incident_id")
            if not incident_id or incident_id in seen_incidents:
                continue
            seen_incidents.add(incident_id)
            deduped.append(r)

        if selected_weeks:
            mondays = sorted(
                (datetime.fromisoformat(iso).date() for iso in selected_weeks), reverse=True
            )
        else:
            mondays = [datetime.fromisoformat(w["iso"]).date() for w in _available_weeks()[1:3]]
        week_labels = {w["iso"]: w["label"] for w in _available_weeks()}
        date_to_monday = {
            (monday + timedelta(days=i)).isoformat(): monday for monday in mondays for i in range(7)
        }

        zero_durations = [0] * len(_DURATION_BUCKET_LABELS)
        counts_by_week_category = {monday: {} for monday in mondays}
        duration_counts_by_week_category = {monday: {} for monday in mondays}
        for r in deduped:
            occurred_at = r.get("occurred_at")
            if not occurred_at:
                continue
            monday = date_to_monday.get(str(occurred_at)[:10])
            if monday is None:
                continue
            categories = [c for c in root_cause_lookup.get(r.get("incident_id"), ["None"]) if c != "None"]
            resolved_at = r.get("resolved_at")
            bucket_index = None
            if resolved_at:
                try:
                    occurred_dt = datetime.fromisoformat(str(occurred_at)[:19])
                    resolved_dt = datetime.fromisoformat(str(resolved_at)[:19])
                    hours = (resolved_dt - occurred_dt).total_seconds() / 3600
                except ValueError:
                    hours = -1
                if hours >= 0:
                    bucket_index = _duration_bucket_index(hours)
            for category in categories or ["Cancelled/AutoClosed"]:
                counts_by_week_category[monday][category] = (
                    counts_by_week_category[monday].get(category, 0) + 1
                )
                if bucket_index is not None:
                    cat_durations = duration_counts_by_week_category[monday].setdefault(
                        category, list(zero_durations)
                    )
                    cat_durations[bucket_index] += 1

        all_categories = sorted({c for counts in counts_by_week_category.values() for c in counts})
        newest, oldest = (mondays[0], mondays[-1]) if mondays else (None, None)

        breakdown = []
        for category in all_categories:
            newest_count = counts_by_week_category[newest].get(category, 0) if newest else 0
            oldest_count = counts_by_week_category[oldest].get(category, 0) if oldest else 0
            week_counts = [counts_by_week_category[m].get(category, 0) for m in mondays]
            duration_week_counts = [
                duration_counts_by_week_category[m].get(category, zero_durations) for m in mondays
            ]
            newest_durations = (
                duration_counts_by_week_category[newest].get(category, zero_durations) if newest else zero_durations
            )
            oldest_durations = (
                duration_counts_by_week_category[oldest].get(category, zero_durations) if oldest else zero_durations
            )
            breakdown.append({
                "category": category,
                "weeks": [
                    {
                        "label": week_labels.get(m.isoformat(), f"{m.strftime('%b')} {m.day}"),
                        "count": week_counts[i],
                    }
                    for i, m in enumerate(mondays)
                ],
                "delta": newest_count - oldest_count,
                "durations": [
                    {
                        "label": bucket_label,
                        "token": _DURATION_BUCKET_TOKENS[bucket_label],
                        "weeks": [
                            {
                                "label": week_labels.get(m.isoformat(), f"{m.strftime('%b')} {m.day}"),
                                "count": duration_week_counts[i][bucket_index],
                            }
                            for i, m in enumerate(mondays)
                        ],
                        "delta": newest_durations[bucket_index] - oldest_durations[bucket_index],
                    }
                    for bucket_index, bucket_label in enumerate(_DURATION_BUCKET_LABELS)
                ],
            })
        breakdown.sort(key=lambda b: b["delta"], reverse=True)

        return {
            "week_labels": [week_labels.get(m.isoformat(), f"{m.strftime('%b')} {m.day}") for m in mondays],
            "categories": breakdown,
        }

    def get_site_down_root_cause_duration_details(
        self, badge_type=None, category=None, site_code=None, weeks=None
    ):
        """Rows behind one duration-bucket cell in the Root Cause
        Breakdown table's expanded category panel (get_site_down_
        root_cause_weekly_breakdown()'s own "durations" list) —
        badge_type is a _DURATION_BUCKET_TOKENS value (e.g. "lt15m"),
        `category` the Root Cause Category name (or "Cancelled/AutoClosed")
        the cell's own row belongs to — two separate params, same
        reasoning as get_incident_volume_day_duration_details()'s own
        `categories` param: every category's bucket cells share the
        same badge_type shape, so category is what actually tells two
        categories' same-bucket cells apart. `site_code`/`weeks`, if
        given, match whatever filters were active on the card. None if
        badge_type isn't a real duration token. Narrowed to the top 10
        sites when no site_code is given, same population as the rest
        of this card — see get_site_down_root_cause_breakdown()'s own
        docstring for why."""
        token_to_label = {v: k for k, v in _DURATION_BUCKET_TOKENS.items()}
        if badge_type not in token_to_label:
            return None
        bucket_index = _DURATION_BUCKET_LABELS.index(token_to_label[badge_type])

        rows, _selected_weeks = self._filter_site_down_rows_by_weeks(
            self._site_down_duration_weekly_rows(), weeks
        )
        if site_code:
            rows = [r for r in rows if r.get("site_code") == site_code]
        else:
            top10_codes = {code for (code, _name), _count in self._rank_site_down_codes(rows)[:10]}
            rows = [r for r in rows if r.get("site_code") in top10_codes]
        root_cause_lookup = self._root_cause_lookup()

        seen_incidents = set()
        deduped = []
        for r in rows:
            incident_id = r.get("incident_id")
            if not incident_id or incident_id in seen_incidents:
                continue
            seen_incidents.add(incident_id)
            categories = [c for c in root_cause_lookup.get(incident_id, ["None"]) if c != "None"]
            if category not in (categories or ["Cancelled/AutoClosed"]):
                continue
            occurred_at, resolved_at = r.get("occurred_at"), r.get("resolved_at")
            if not (occurred_at and resolved_at):
                continue
            try:
                occurred_dt = datetime.fromisoformat(str(occurred_at)[:19])
                resolved_dt = datetime.fromisoformat(str(resolved_at)[:19])
            except ValueError:
                continue
            hours = (resolved_dt - occurred_dt).total_seconds() / 3600
            if hours < 0 or _duration_bucket_index(hours) != bucket_index:
                continue
            deduped.append(r)

        return self._with_duration_display_and_root_cause(deduped, root_cause_lookup)

    # ── Site-Down Root Cause — Breakdown (the OTHER donut) ──
    # Same real data as Root Cause Breakdown above, just following
    # whichever week(s) "Site-Down Duration — Weekly Trend"'s own
    # Compare Weeks picker (site_down_duration_week, already multi-
    # select) has selected — occurred_at based, unioned across however
    # many weeks are checked, same "pick several, union them" idea as
    # AlarmService.filter_congestion_weeks() for a different card — and
    # with no site concept — this donut isn't linked to Top 10 Site Down.
    # `duration_bucket`, if given, is the cross-filter from that same
    # card's own x-axis bucket labels (see dashboard.py's
    # _performance_cards_context()) — same cross-filter idea as Root
    # Cause Breakdown's own site_code param, just a duration bucket
    # instead of a site.

    @staticmethod
    def _filter_rows_by_weeks(rows, weeks):
        """Narrows `rows` to the UNION of `weeks` (ISO Monday dates) by
        closed_at — matches _bucket_site_down_duration()'s own week
        anchor exactly, since every caller of this helper is a
        "Site-Down Root Cause — Breakdown" view into THAT SAME "Site-
        Down Duration — Weekly Trend" population (not a standalone
        week filter). Using occurred_at here instead (as an earlier
        version did) made the two cards silently disagree on which
        incidents belong to "Week 40": an incident that occurred in
        Week 40 but wasn't closed until later counted toward Root
        Cause's Week 40 total while sitting in Duration Trend's later
        week instead — confirmed live (5987 Root Cause vs 3987/3804
        Duration Trend for the same 2 "weeks"). Falls back to
        _resolve_selected_weeks([])'s own "last 2 complete weeks"
        default when `weeks` is empty/every value invalid — same
        default every other Compare Weeks picker on this dashboard
        uses. Returns `(filtered_rows, mondays)` — `mondays` (newest
        first) is what the card's own subtitle label is built from."""
        mondays = _resolve_selected_weeks(weeks)
        date_strs = {
            (monday + timedelta(days=i)).isoformat() for monday in mondays for i in range(7)
        }
        return [r for r in rows if str(r.get("closed_at") or "")[:10] in date_strs], mondays

    @staticmethod
    def _filter_rows_by_duration_bucket(rows, duration_bucket):
        """Narrows `rows` to incidents whose (resolved_at - occurred_at)
        falls in `duration_bucket` (a _DURATION_BUCKET_LABELS value) —
        a row with no resolved_at yet can't match any bucket, so it's
        dropped, same "no computable duration" rule used everywhere
        else duration gets bucketed in this file. No-op (every row
        kept) if `duration_bucket` isn't a real bucket label."""
        if duration_bucket not in _DURATION_BUCKET_LABELS:
            return rows
        matched = []
        for r in rows:
            occurred_at, resolved_at = r.get("occurred_at"), r.get("resolved_at")
            if not (occurred_at and resolved_at):
                continue
            try:
                occurred_dt = datetime.fromisoformat(str(occurred_at)[:19])
                resolved_dt = datetime.fromisoformat(str(resolved_at)[:19])
            except ValueError:
                continue
            hours = (resolved_dt - occurred_dt).total_seconds() / 3600
            if hours >= 0 and _DURATION_BUCKET_LABELS[_duration_bucket_index(hours)] == duration_bucket:
                matched.append(r)
        return matched

    def get_site_down_root_cause_week_breakdown(self, duration_bucket=None, weeks=None):
        """Week-scoped equivalent of get_site_down_root_cause_
        breakdown() — for "Site-Down Root Cause — Breakdown"'s own pie.
        See that method's docstring for the shared "Cancelled/AutoClosed"
        slice/pct treatment; the real differences are the population
        (whichever week(s) are selected, every site — not top-10-sites)
        and the optional `duration_bucket` cross-filter from "Site-Down
        Duration — Weekly Trend"'s x-axis labels. `weeks` is that same
        card's own Compare Weeks selection (site_down_duration_week) —
        see _filter_rows_by_weeks()'s own docstring for the default."""
        rows, mondays = self._filter_rows_by_weeks(self._site_down_duration_weekly_rows(), weeks)
        rows = self._filter_rows_by_duration_bucket(rows, duration_bucket)
        root_cause_lookup = self._root_cause_lookup()

        counts = {}
        no_cause = 0
        seen_incidents = set()
        for r in rows:
            incident_id = r.get("incident_id")
            if not incident_id or incident_id in seen_incidents:
                continue
            seen_incidents.add(incident_id)
            categories = [c for c in root_cause_lookup.get(incident_id, ["None"]) if c != "None"]
            if not categories:
                no_cause += 1
                continue
            for category in categories:
                counts[category] = counts.get(category, 0) + 1

        ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
        total_with_cause = sum(counts.values())
        total_overall = total_with_cause + no_cause
        categories = [
            {
                "category": category,
                "count": count,
                "pct": round(count / total_overall * 100, 1) if total_overall else 0,
                "note": None,
            }
            for category, count in ranked
        ]
        if no_cause:
            categories.append({
                "category": "Cancelled/AutoClosed",
                "count": no_cause,
                "pct": round(no_cause / total_overall * 100, 1) if total_overall else 0,
                "note": None,
            })
        week_labels = {w["iso"]: w["label"] for w in _available_weeks()}
        return {
            "categories": categories,
            "total_with_cause": total_with_cause,
            "total_no_cause": no_cause,
            "total_overall": total_overall,
            "duration_bucket": duration_bucket if duration_bucket in _DURATION_BUCKET_LABELS else None,
            "weeks_label": ", ".join(
                week_labels.get(m.isoformat(), f"{m.strftime('%b')} {m.day}") for m in mondays
            ),
        }

    def get_site_down_root_cause_week_table(self, duration_bucket=None, weeks=None):
        """Week-scoped equivalent of get_site_down_root_cause_weekly_
        breakdown()'s table — ONE COLUMN PER selected week (e.g.
        checking Week 38/39/40 on "Site-Down Duration — Weekly Trend"
        shows all 3 as their own columns here, not summed into one),
        same dynamic-width-table pattern that method already uses, just
        driven by this card's own `weeks` (site_down_duration_week)
        instead of a fixed "Last week vs Week N" pair — see
        _filter_rows_by_weeks()'s own docstring for the "last 2
        complete weeks" fallback when nothing's selected. "Change" is
        newest selected week minus oldest (0 when only one week is
        selected — there's nothing else to compare it against). Each
        category row still carries its own "durations" list (≤15m..
        >24h) for the same expand-to-duration-breakdown accordion the
        other card's table already has; each week's count and each
        duration cell still link to the SAME category-level drilldown
        (not narrowed to just that one week — same simplification the
        other table's own week columns already make, see that
        method's docstring)."""
        rows, mondays = self._filter_rows_by_weeks(self._site_down_duration_weekly_rows(), weeks)
        rows = self._filter_rows_by_duration_bucket(rows, duration_bucket)
        root_cause_lookup = self._root_cause_lookup()

        seen_incidents = set()
        deduped = []
        for r in rows:
            incident_id = r.get("incident_id")
            if not incident_id or incident_id in seen_incidents:
                continue
            seen_incidents.add(incident_id)
            deduped.append(r)

        week_labels = {w["iso"]: w["label"] for w in _available_weeks()}
        date_to_monday = {
            (monday + timedelta(days=i)).isoformat(): monday for monday in mondays for i in range(7)
        }

        zero_durations = [0] * len(_DURATION_BUCKET_LABELS)
        counts_by_week_category = {monday: {} for monday in mondays}
        duration_counts_by_week_category = {monday: {} for monday in mondays}
        for r in deduped:
            occurred_at = r.get("occurred_at")
            if not occurred_at:
                continue
            monday = date_to_monday.get(str(occurred_at)[:10])
            if monday is None:
                continue
            categories = [c for c in root_cause_lookup.get(r.get("incident_id"), ["None"]) if c != "None"]
            resolved_at = r.get("resolved_at")
            bucket_index = None
            if resolved_at:
                try:
                    occurred_dt = datetime.fromisoformat(str(occurred_at)[:19])
                    resolved_dt = datetime.fromisoformat(str(resolved_at)[:19])
                    hours = (resolved_dt - occurred_dt).total_seconds() / 3600
                except (ValueError, TypeError):
                    hours = -1
                if hours >= 0:
                    bucket_index = _duration_bucket_index(hours)
            for category in categories or ["Cancelled/AutoClosed"]:
                counts_by_week_category[monday][category] = (
                    counts_by_week_category[monday].get(category, 0) + 1
                )
                if bucket_index is not None:
                    cat_durations = duration_counts_by_week_category[monday].setdefault(
                        category, list(zero_durations)
                    )
                    cat_durations[bucket_index] += 1

        all_categories = sorted({c for counts in counts_by_week_category.values() for c in counts})
        newest, oldest = (mondays[0], mondays[-1]) if mondays else (None, None)

        breakdown = []
        for category in all_categories:
            newest_count = counts_by_week_category[newest].get(category, 0) if newest else 0
            oldest_count = counts_by_week_category[oldest].get(category, 0) if oldest else 0
            week_counts = [counts_by_week_category[m].get(category, 0) for m in mondays]
            duration_week_counts = [
                duration_counts_by_week_category[m].get(category, zero_durations) for m in mondays
            ]
            newest_durations = (
                duration_counts_by_week_category[newest].get(category, zero_durations) if newest else zero_durations
            )
            oldest_durations = (
                duration_counts_by_week_category[oldest].get(category, zero_durations) if oldest else zero_durations
            )
            breakdown.append({
                "category": category,
                "weeks": [
                    {
                        "label": week_labels.get(m.isoformat(), f"{m.strftime('%b')} {m.day}"),
                        "count": week_counts[i],
                    }
                    for i, m in enumerate(mondays)
                ],
                "delta": newest_count - oldest_count,
                "durations": [
                    {
                        "label": bucket_label,
                        "token": _DURATION_BUCKET_TOKENS[bucket_label],
                        "weeks": [
                            {
                                "label": week_labels.get(m.isoformat(), f"{m.strftime('%b')} {m.day}"),
                                "count": duration_week_counts[i][bucket_index],
                            }
                            for i, m in enumerate(mondays)
                        ],
                        "delta": newest_durations[bucket_index] - oldest_durations[bucket_index],
                    }
                    for bucket_index, bucket_label in enumerate(_DURATION_BUCKET_LABELS)
                ],
            })
        breakdown.sort(key=lambda b: b["delta"], reverse=True)

        return {
            "week_labels": [week_labels.get(m.isoformat(), f"{m.strftime('%b')} {m.day}") for m in mondays],
            "categories": breakdown,
        }

    def get_site_down_root_cause_week_details(self, badge_type=None, duration_bucket=None, weeks=None):
        """Rows behind one "Site-Down Root Cause — Breakdown" slice —
        same badge_type convention as get_site_down_root_cause_details()
        (a Root Cause Category name, or "Cancelled/AutoClosed"), scoped to
        whichever week(s) are selected (see get_site_down_root_cause_
        week_breakdown()) and optionally the same `duration_bucket`
        cross-filter."""
        rows, _mondays = self._filter_rows_by_weeks(self._site_down_duration_weekly_rows(), weeks)
        rows = self._filter_rows_by_duration_bucket(rows, duration_bucket)
        root_cause_lookup = self._root_cause_lookup()

        seen_incidents = set()
        deduped = []
        for r in rows:
            incident_id = r.get("incident_id")
            if not incident_id or incident_id in seen_incidents:
                continue
            seen_incidents.add(incident_id)
            deduped.append(r)

        if badge_type == "Cancelled/AutoClosed":
            deduped = [
                r
                for r in deduped
                if all(c == "None" for c in root_cause_lookup.get(r.get("incident_id"), ["None"]))
            ]
        elif badge_type:
            valid_categories = {
                category
                for categories in root_cause_lookup.values()
                for category in categories
                if category != "None"
            }
            if badge_type not in valid_categories:
                return None
            deduped = [
                r for r in deduped if badge_type in root_cause_lookup.get(r.get("incident_id"), [])
            ]
        else:
            deduped = [
                r
                for r in deduped
                if any(c != "None" for c in root_cause_lookup.get(r.get("incident_id"), ["None"]))
            ]

        return self._with_duration_display_and_root_cause(deduped, root_cause_lookup)

    def get_site_down_root_cause_week_duration_details(self, badge_type=None, category=None, weeks=None):
        """Rows behind one duration-bucket cell in the Site-Down Root
        Cause — Breakdown table's expanded category panel — same shape
        as get_site_down_root_cause_duration_details(), just scoped to
        whichever week(s) are selected instead of 30 days/top-10-sites."""
        token_to_label = {v: k for k, v in _DURATION_BUCKET_TOKENS.items()}
        if badge_type not in token_to_label:
            return None
        bucket_index = _DURATION_BUCKET_LABELS.index(token_to_label[badge_type])

        rows, _mondays = self._filter_rows_by_weeks(self._site_down_duration_weekly_rows(), weeks)
        root_cause_lookup = self._root_cause_lookup()

        seen_incidents = set()
        deduped = []
        for r in rows:
            incident_id = r.get("incident_id")
            if not incident_id or incident_id in seen_incidents:
                continue
            seen_incidents.add(incident_id)
            categories = [c for c in root_cause_lookup.get(incident_id, ["None"]) if c != "None"]
            if category not in (categories or ["Cancelled/AutoClosed"]):
                continue
            occurred_at, resolved_at = r.get("occurred_at"), r.get("resolved_at")
            if not (occurred_at and resolved_at):
                continue
            try:
                occurred_dt = datetime.fromisoformat(str(occurred_at)[:19])
                resolved_dt = datetime.fromisoformat(str(resolved_at)[:19])
            except ValueError:
                continue
            hours = (resolved_dt - occurred_dt).total_seconds() / 3600
            if hours < 0 or _duration_bucket_index(hours) != bucket_index:
                continue
            deduped.append(r)

        return self._with_duration_display_and_root_cause(deduped, root_cause_lookup)

    def get_volume_trend_details(
        self, badge_type=None, categories=None, severities=None, provinces=None, vendors=None
    ):
        """Rows for one "Incident Volume" day/week (badge_type
        "date_YYYY-MM-DD" or "week_YYYY-MM-DD" — the latter from the
        "By Category"/"By Severity"/"By Province"/"By Vendor" popups'
        own week-total cells, see _filter_rows_by_date()), or every row
        if badge_type is empty. None if badge_type isn't in either
        form. `categories`/`severities`/`provinces`/`vendors` (each a
        list) further narrow to rows matching any one of that field's
        values, combinable with badge_type and each other; empty/None
        means no filter on that field."""
        rows = self.get_created_trend_rows()
        if badge_type:
            rows = _filter_rows_by_date(rows, "created_at", badge_type)
            if rows is None:
                return None
        rows = _filter_rows_by_categories(rows, categories)
        if severities:
            rows = [r for r in rows if r.get("severity") in severities]
        if provinces:
            rows = [r for r in rows if r.get("province") in provinces]
        if vendors:
            rows = [r for r in rows if r.get("vendor") in vendors]
        return rows

    def get_volume_trend_categories(self, rows=None):
        """Every distinct Incident Category present in incident_created_trend,
        for the drilldown's / card header's category filter options.
        `rows`, if given (see get_created_trend_rows()), is used instead
        of fetching."""
        rows = rows if rows is not None else self.get_created_trend_rows()
        return sorted({r["category"] for r in rows if r.get("category")})

    def get_volume_trend_field_values(self, field, rows=None):
        """Every distinct value of `field` (e.g. "severity", "province",
        "vendor") present in incident_created_trend, for the "Incident
        Volume" drilldown's Severity/Province/Vendor filter checkbox
        options — same "actually present in the data, not a fixed list"
        convention as get_volume_trend_categories() above, generalized
        since the drilldown now has more than one filterable field.

        `field == "severity"` is the one exception to "actually present,
        not a fixed list": fixed to _SEVERITY_ORDER (urgency rank,
        Warning excluded) by request, rather than whatever's alphabetically
        present."""
        if field == "severity":
            return list(_SEVERITY_ORDER)
        rows = rows if rows is not None else self.get_created_trend_rows()
        return sorted({r[field] for r in rows if r.get(field)})

    def get_closed_trend_details(self, badge_type=None, categories=None):
        """Rows for one "Incidents Closed" bar (badge_type "date_YYYY-MM-DD"),
        or every row if badge_type is empty. None if badge_type isn't in
        that form. `categories` (a list) further narrows to rows matching
        any one of them, combinable with badge_type; empty/None means no
        category filter."""
        rows = self.get_closed_trend_rows()
        if badge_type:
            rows = _filter_rows_by_date(rows, "closed_at", badge_type)
            if rows is None:
                return None
        rows = _filter_rows_by_categories(rows, categories)
        return rows

    def get_closed_trend_categories(self, rows=None):
        """Every distinct Incident Category present in incident_closed_trend,
        for the drilldown's / card header's category filter options.
        `rows`, if given (see get_closed_trend_rows()), is used instead
        of fetching."""
        rows = rows if rows is not None else self.get_closed_trend_rows()
        return sorted({r["category"] for r in rows if r.get("category")})

    def get_details(self, badge_type=None):
        """Drilldown rows for one Incident badge or Age bucket, with
        outage_min filled in — or every row if badge_type is empty.
        None only if badge_type is given but unrecognized."""
        rows = self.get_incident_status_rows()
        if not badge_type:
            filtered = rows
        elif badge_type in _AGE_BUCKET_RANGES:
            filtered = [
                r for r in rows
                if r.get("category") == "Site Down" and _matches_age_bucket(r, badge_type)
            ]
        else:
            filters = BADGE_FILTERS.get(badge_type)
            if filters is None:
                return None
            filtered = [r for r in rows if _matches(r, filters)]
        for r in filtered:
            r["outage_min"] = elapsed_minutes(r.get("occurred_at"))
        return filtered

    def get_incident_site_down_counts(self):
        """Badge counts for the "Incident Site Down" card (Hub,
        Diamond, Gold, Silver, Bronze)."""
        rows = self.site_down_cache_repository.fetch_all(_SITE_DOWN_TABLE)
        counts = {
            grade: sum(1 for r in rows if r.get("site_grade") == label)
            for grade, label in _SITE_GRADE_BADGES.items()
        }
        counts["hub"] = sum(
            1 for r in rows if (r.get("hub_site") or "").strip() not in ("", "Not Hub")
        )
        return counts

    def get_incident_site_down_details(self, badge_type=None):
        """Rows behind the "Incident Site Down" card, with outage_min
        filled in, narrowed to `badge_type` if given."""
        rows = self.site_down_cache_repository.fetch_all(_SITE_DOWN_TABLE)
        if badge_type:
            rows = [r for r in rows if _matches_site_down_badge(r, badge_type)]
        for r in rows:
            r["outage_min"] = elapsed_minutes(r.get("occurred_at"))
        return rows
