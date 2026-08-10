"""Tests for seconds_until_next_aligned_time()'s offset_seconds parameter —
added so background jobs (Site, Incident, ape_alarm, VIP Alarm, VIP Site,
etc.) that all used to target the exact same clock-aligned instant every
cycle can each land a few seconds apart instead, spreading their local
database writes (and the browser's own auto-reload, see
app/routes/dashboard.py's index()) across the cycle rather than
concentrating them all in one moment.
"""

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.services.scheduler_utils import seconds_until_next_aligned_time

_TZ = "UTC"


def _frozen_at(hour, minute, second):
    return datetime(2026, 1, 1, hour, minute, second, tzinfo=ZoneInfo(_TZ))


def test_default_offset_matches_original_unoffset_behavior():
    """offset_seconds defaults to 0 — every existing caller that doesn't
    pass it must see byte-identical behavior to before this parameter
    existed."""
    with patch("app.services.scheduler_utils.datetime") as mock_dt:
        mock_dt.now.return_value = _frozen_at(0, 2, 0)
        without_param = seconds_until_next_aligned_time(300, _TZ)
        with_zero = seconds_until_next_aligned_time(300, _TZ, offset_seconds=0)

    assert without_param == with_zero == 180


def test_offset_seconds_delays_the_target_by_exactly_that_much():
    with patch("app.services.scheduler_utils.datetime") as mock_dt:
        mock_dt.now.return_value = _frozen_at(0, 2, 0)
        no_offset = seconds_until_next_aligned_time(300, _TZ)
        offset_30 = seconds_until_next_aligned_time(300, _TZ, offset_seconds=30)

    assert offset_30 - no_offset == 30


def test_two_jobs_with_different_offsets_never_land_on_the_same_instant():
    """The real-world point of this feature: two jobs sharing the same
    interval but different offsets (e.g. Site at 0, Incident at 30) must
    resolve to two different absolute target times, not collide."""
    now = _frozen_at(13, 47, 22)
    with patch("app.services.scheduler_utils.datetime") as mock_dt:
        mock_dt.now.return_value = now
        site_delay = seconds_until_next_aligned_time(300, _TZ, offset_seconds=0)
        incident_delay = seconds_until_next_aligned_time(300, _TZ, offset_seconds=30)

    assert site_delay != incident_delay


def test_offset_wraps_correctly_across_the_cycle_boundary():
    """A large enough offset relative to `now` must still resolve to a
    sensible, positive wait time via Python's floor-mod — not a negative
    or nonsensical value."""
    with patch("app.services.scheduler_utils.datetime") as mock_dt:
        mock_dt.now.return_value = _frozen_at(0, 0, 5)
        delay = seconds_until_next_aligned_time(300, _TZ, offset_seconds=90)

    assert delay == 85
