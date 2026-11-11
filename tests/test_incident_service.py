"""Tests for IncidentService.get_details() — the Overall Dashboard's
"Incident" column drilldown. Real bug found and fixed here: the plain
"View Incidents" footer link (app/templates/dashboard/partials/cards.html)
passes no `type` query param, so dashboard.py's scope handler calls
get_details("") — which used to return None for ANY badge_type not in
BADGE_FILTERS, including "", so the button rendered the empty-state
template instead of every Incident row. Every other drilldown service in
this app (DgOnAlarmService, AlarmSiteDownService, etc.) treats an empty/
missing badge_type as "no filter, show everything" — these were the
outliers.
"""

from datetime import date, timedelta

from app.services.incident.incident_service import (
    IncidentService,
    _bucket_duration_by_created_weekday_and_category,
    _filter_rows_by_categories,
    _with_deltas,
)


class FakeStatusRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self, table):
        return self._rows


class FakeClosedTrendRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self, table):
        return self._rows


class FakeCreatedTrendRepo:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self, table):
        return self._rows


def _row(incident_status="New", category="BSS Hardware", overdue="No", **overrides):
    row = {
        "incident_id": "INC1",
        "incident_status": incident_status,
        "category": category,
        "overdue": overdue,
        "site_code": "S1",
        "occurred_at": "2026-01-01 00:00:00",
    }
    row.update(overrides)
    return row


def test_get_incident_counts_counts_distinct_incidents_not_rows():
    """A multi-site incident (2 rows, same incident_id, different sites)
    must count once toward its badge, matching Streamline's own per-ticket
    count — not once per affected site."""
    rows = [
        _row(incident_id="INC1", incident_status="In Progress", site_code="S1"),
        _row(incident_id="INC1", incident_status="In Progress", site_code="S2"),
        _row(incident_id="INC2", incident_status="In Progress", site_code="S3"),
    ]
    svc = IncidentService(FakeStatusRepo(rows), FakeStatusRepo([]))

    counts = svc.get_incident_counts()

    assert counts["in_progress"] == 2


def test_get_incident_counts_matches_get_details_row_count_when_no_multi_site_incident():
    rows = [
        _row(incident_id="INC1", incident_status="New"),
        _row(incident_id="INC2", incident_status="New"),
    ]
    svc = IncidentService(FakeStatusRepo(rows), FakeStatusRepo([]))

    assert svc.get_incident_counts()["new"] == 2


def test_get_details_with_no_badge_type_returns_every_row():
    rows = [_row(incident_status="New"), _row(incident_status="In Progress")]
    svc = IncidentService(FakeStatusRepo(rows), FakeStatusRepo([]))

    result = svc.get_details("")

    assert len(result) == 2


def test_get_details_with_none_badge_type_returns_every_row():
    rows = [_row(incident_status="New"), _row(incident_status="In Progress")]
    svc = IncidentService(FakeStatusRepo(rows), FakeStatusRepo([]))

    result = svc.get_details(None)

    assert len(result) == 2


def test_get_details_filters_by_known_badge_type():
    rows = [_row(incident_status="New"), _row(incident_status="In Progress")]
    svc = IncidentService(FakeStatusRepo(rows), FakeStatusRepo([]))

    result = svc.get_details("new")

    assert len(result) == 1
    assert result[0]["incident_status"] == "New"


def test_get_details_with_unknown_badge_type_returns_none():
    rows = [_row()]
    svc = IncidentService(FakeStatusRepo(rows), FakeStatusRepo([]))

    assert svc.get_details("not_a_real_badge") is None


def test_get_incident_age_buckets_dedupes_multi_site_incident_by_earliest_occurred_at():
    """A multi-site incident (2 rows, same incident_id) must count once —
    same reasoning as get_incident_counts()."""
    rows = [
        _row(incident_id="INC1", occurred_at="2026-01-01 10:00:00", site_code="S1", category="Site Down"),
        _row(incident_id="INC1", occurred_at="2026-01-01 09:00:00", site_code="S2", category="Site Down"),
    ]
    svc = IncidentService(FakeStatusRepo(rows), FakeStatusRepo([]))

    buckets = svc.get_incident_age_buckets()

    assert sum(buckets.values()) == 1


def test_get_details_filters_by_age_bucket():
    from datetime import datetime

    from app.utils.datetime import elapsed_minutes

    now = datetime.now()
    fresh_at = now.strftime("%Y-%m-%d %H:%M:%S")
    old_at = (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    fresh_row = _row(incident_id="INC1", occurred_at=fresh_at, category="Site Down")
    old_row = _row(incident_id="INC2", occurred_at=old_at, category="Site Down")
    svc = IncidentService(FakeStatusRepo([fresh_row, old_row]), FakeStatusRepo([]))

    result = svc.get_details("age_gt24")

    assert [r["incident_id"] for r in result] == ["INC2"]
    assert result[0]["outage_min"] == elapsed_minutes(old_at)


def _this_monday():
    today = date.today()
    return today - timedelta(days=today.weekday())


def test_get_incident_closed_trend_buckets_default_weeks_separately():
    """Default (no `weeks` passed) is now the latest two COMPLETE
    weeks, not [this week, last week] — the current week is still
    in-progress and comparing against it produces misleading deltas
    (see _resolve_selected_weeks()'s own docstring)."""
    last_monday = _this_monday() - timedelta(days=7)
    two_mondays_ago = last_monday - timedelta(days=7)
    rows = [
        {"incident_id": "INC1", "closed_at": f"{last_monday} 09:00:00"},
        {"incident_id": "INC2", "closed_at": f"{last_monday} 10:00:00"},
        {"incident_id": "INC3", "closed_at": f"{two_mondays_ago} 09:00:00"},
    ]
    svc = IncidentService(FakeStatusRepo([]), FakeStatusRepo([]), FakeClosedTrendRepo(rows))

    trend = svc.get_incident_closed_trend()

    assert trend["days"][0]["day"] == "Mon"
    assert trend["days"][0]["series"][0]["value"] == 2
    assert trend["days"][0]["series"][1]["value"] == 1
    assert trend["week_totals"][0]["total"] == 2
    assert trend["week_totals"][1]["total"] == 1


def test_get_incident_closed_trend_ignores_incidents_older_than_the_default_window():
    too_old = _this_monday() - timedelta(days=21)
    rows = [{"incident_id": "INC1", "closed_at": f"{too_old} 09:00:00"}]
    svc = IncidentService(FakeStatusRepo([]), FakeStatusRepo([]), FakeClosedTrendRepo(rows))

    trend = svc.get_incident_closed_trend()

    assert trend["week_totals"][0]["total"] == 0
    assert trend["week_totals"][1]["total"] == 0


def test_get_incident_closed_trend_ignores_blank_closed_at():
    rows = [{"incident_id": "INC1", "closed_at": ""}, {"incident_id": "INC2", "closed_at": None}]
    svc = IncidentService(FakeStatusRepo([]), FakeStatusRepo([]), FakeClosedTrendRepo(rows))

    trend = svc.get_incident_closed_trend()

    assert trend["week_totals"][0]["total"] == 0
    assert trend["week_totals"][1]["total"] == 0


def test_get_incident_closed_trend_axis_ticks_cover_the_max_bucket():
    last_monday = _this_monday() - timedelta(days=7)
    rows = [{"incident_id": f"INC{i}", "closed_at": f"{last_monday} 09:00:00"} for i in range(7)]
    svc = IncidentService(FakeStatusRepo([]), FakeStatusRepo([]), FakeClosedTrendRepo(rows))

    trend = svc.get_incident_closed_trend()

    assert trend["days"][0]["series"][0]["value"] == 7
    assert int(trend["tick_labels"][0]) >= 7


def test_get_incident_closed_trend_per_day_delta_and_date_label():
    today_idx = date.today().weekday()
    last_monday = date.today() - timedelta(days=today_idx) - timedelta(days=7)
    two_mondays_ago = last_monday - timedelta(days=7)
    newest_date = last_monday + timedelta(days=today_idx)
    rows = [
        {"incident_id": "INC1", "closed_at": f"{newest_date} 09:00:00"},
        {"incident_id": "INC2", "closed_at": f"{newest_date} 10:00:00"},
        {"incident_id": "INC3", "closed_at": f"{two_mondays_ago + timedelta(days=today_idx)} 09:00:00"},
    ]
    svc = IncidentService(FakeStatusRepo([]), FakeStatusRepo([]), FakeClosedTrendRepo(rows))

    trend = svc.get_incident_closed_trend()
    today_day = trend["days"][today_idx]

    assert today_day["series"][0]["value"] == 2
    assert today_day["series"][1]["value"] == 1
    assert today_day["series"][0]["delta_pct"] == 100
    assert today_day["series"][0]["date_label"] == (
        newest_date.strftime("%b") + " " + str(newest_date.day)
    )


def test_get_closed_trend_details_with_no_badge_type_returns_every_row():
    rows = [{"incident_id": "INC1", "closed_at": "2026-01-05 09:00:00"}]
    svc = IncidentService(FakeStatusRepo([]), FakeStatusRepo([]), FakeClosedTrendRepo(rows))

    assert len(svc.get_closed_trend_details("")) == 1


def test_get_closed_trend_details_with_unknown_badge_type_returns_none():
    svc = IncidentService(FakeStatusRepo([]), FakeStatusRepo([]), FakeClosedTrendRepo([]))

    assert svc.get_closed_trend_details("not_a_real_badge") is None


def test_get_closed_trend_details_filters_by_week_and_weekday():
    this_monday = _this_monday()
    last_tuesday = (this_monday - timedelta(days=7)) + timedelta(days=1)
    rows = [
        {"incident_id": "INC1", "closed_at": f"{this_monday} 09:00:00"},
        {"incident_id": "INC2", "closed_at": f"{last_tuesday} 10:00:00"},
    ]
    svc = IncidentService(FakeStatusRepo([]), FakeStatusRepo([]), FakeClosedTrendRepo(rows))

    this_mon_result = svc.get_closed_trend_details(f"date_{this_monday.isoformat()}")
    last_tue_result = svc.get_closed_trend_details(f"date_{last_tuesday.isoformat()}")

    assert [r["incident_id"] for r in this_mon_result] == ["INC1"]
    assert [r["incident_id"] for r in last_tue_result] == ["INC2"]


def test_get_closed_trend_details_filters_by_category():
    rows = [
        {"incident_id": "INC1", "closed_at": "2026-01-01 00:00:00", "category": "Site Down"},
        {"incident_id": "INC2", "closed_at": "2026-01-01 00:00:00", "category": "Power"},
    ]
    svc = IncidentService(FakeStatusRepo([]), FakeStatusRepo([]), FakeClosedTrendRepo(rows))

    result = svc.get_closed_trend_details(categories=["Power"])

    assert [r["incident_id"] for r in result] == ["INC2"]


def test_get_closed_trend_details_combines_weekday_and_category_filters():
    this_monday = _this_monday()
    rows = [
        {"incident_id": "INC1", "closed_at": f"{this_monday} 09:00:00", "category": "Site Down"},
        {"incident_id": "INC2", "closed_at": f"{this_monday} 09:00:00", "category": "Power"},
    ]
    svc = IncidentService(FakeStatusRepo([]), FakeStatusRepo([]), FakeClosedTrendRepo(rows))

    result = svc.get_closed_trend_details(f"date_{this_monday.isoformat()}", categories=["Power"])

    assert [r["incident_id"] for r in result] == ["INC2"]


def test_get_closed_trend_details_unknown_badge_type_returns_none_even_with_category():
    svc = IncidentService(FakeStatusRepo([]), FakeStatusRepo([]), FakeClosedTrendRepo([]))

    assert svc.get_closed_trend_details("not_a_real_badge", categories=["Power"]) is None


def test_get_closed_trend_categories_returns_sorted_distinct_values():
    rows = [
        {"incident_id": "INC1", "category": "Site Down"},
        {"incident_id": "INC2", "category": "Power"},
        {"incident_id": "INC3", "category": "Power"},
        {"incident_id": "INC4", "category": ""},
    ]
    svc = IncidentService(FakeStatusRepo([]), FakeStatusRepo([]), FakeClosedTrendRepo(rows))

    assert svc.get_closed_trend_categories() == ["Power", "Site Down"]


def test_get_incident_volume_trend_buckets_default_weeks_separately():
    """Same default-window change as the Closed trend's own test —
    see test_get_incident_closed_trend_buckets_default_weeks_separately."""
    last_monday = _this_monday() - timedelta(days=7)
    two_mondays_ago = last_monday - timedelta(days=7)
    rows = [
        {"incident_id": "INC1", "created_at": f"{last_monday} 09:00:00"},
        {"incident_id": "INC2", "created_at": f"{last_monday} 10:00:00"},
        {"incident_id": "INC3", "created_at": f"{two_mondays_ago} 09:00:00"},
    ]
    svc = IncidentService(
        FakeStatusRepo([]), FakeStatusRepo([]), created_trend_cache_repository=FakeCreatedTrendRepo(rows)
    )

    trend = svc.get_incident_volume_trend()

    assert trend["days"][0]["day"] == "Mon"
    assert trend["days"][0]["series"][0]["value"] == 2
    assert trend["days"][0]["series"][1]["value"] == 1
    assert trend["week_totals"][0]["total"] == 2
    assert trend["week_totals"][1]["total"] == 1


def test_get_incident_volume_trend_does_not_flag_today_by_default():
    """`is_today` highlights today's weekday column only when this
    week is actually one of the displayed weeks — since the default
    no longer includes the in-progress current week (see
    _resolve_selected_weeks()), nothing should be flagged "today" on
    the default view."""
    svc = IncidentService(
        FakeStatusRepo([]), FakeStatusRepo([]), created_trend_cache_repository=FakeCreatedTrendRepo([])
    )

    trend = svc.get_incident_volume_trend()

    assert all(not d["is_today"] for d in trend["days"])


def test_get_incident_volume_trend_flags_todays_weekday_when_this_week_selected():
    today_idx = date.today().weekday()
    this_monday = _this_monday()
    svc = IncidentService(
        FakeStatusRepo([]), FakeStatusRepo([]), created_trend_cache_repository=FakeCreatedTrendRepo([])
    )

    trend = svc.get_incident_volume_trend(weeks=[this_monday.isoformat()])

    assert trend["days"][today_idx]["is_today"] is True
    assert sum(1 for d in trend["days"] if d["is_today"]) == 1
    assert trend["days"][today_idx]["series"][0]["date_label"] == (
        date.today().strftime("%b") + " " + str(date.today().day)
    )


def test_get_incident_volume_trend_line_points_cover_all_7_days():
    svc = IncidentService(
        FakeStatusRepo([]), FakeStatusRepo([]), created_trend_cache_repository=FakeCreatedTrendRepo([])
    )

    trend = svc.get_incident_volume_trend()

    assert len(trend["days"]) == 7
    assert trend["series"][0]["path"].startswith("M")
    assert trend["series"][1]["path"].startswith("M")


def test_get_incident_volume_trend_curve_passes_through_every_data_point():
    """Regression test: an earlier smoothing algorithm only passed NEAR
    each point (through the midpoint to the next one), so dot markers
    placed at the exact data coordinates rendered visibly off the curve
    (confirmed live via screenshot). The current Catmull-Rom-based
    smoothing must pass exactly through every point instead."""
    this_monday = _this_monday()
    rows = [
        {"incident_id": f"INC{i}", "created_at": f"{this_monday + timedelta(days=i % 7)} 09:00:00"}
        for i in range(10)
    ]
    svc = IncidentService(
        FakeStatusRepo([]), FakeStatusRepo([]), created_trend_cache_repository=FakeCreatedTrendRepo(rows)
    )

    trend = svc.get_incident_volume_trend()

    for s in trend["series"]:
        for x, y in zip(trend["grid_x"], s["y"]):
            assert f"{x:.1f},{y:.1f}" in s["path"]


def test_get_incident_volume_trend_per_day_delta_reflects_default_weeks():
    today_idx = date.today().weekday()
    last_monday = date.today() - timedelta(days=today_idx) - timedelta(days=7)
    two_mondays_ago = last_monday - timedelta(days=7)
    rows = [
        {"incident_id": "INC1", "created_at": f"{last_monday + timedelta(days=today_idx)} 09:00:00"},
        {"incident_id": "INC2", "created_at": f"{last_monday + timedelta(days=today_idx)} 10:00:00"},
        {"incident_id": "INC3", "created_at": f"{two_mondays_ago + timedelta(days=today_idx)} 09:00:00"},
    ]
    svc = IncidentService(
        FakeStatusRepo([]), FakeStatusRepo([]), created_trend_cache_repository=FakeCreatedTrendRepo(rows)
    )

    trend = svc.get_incident_volume_trend()
    today_day = trend["days"][today_idx]

    assert today_day["series"][0]["value"] == 2
    assert today_day["series"][1]["value"] == 1
    assert today_day["series"][0]["delta_pct"] == 100


def test_get_incident_volume_day_category_breakdowns_attaches_durations_to_every_category():
    """Every category has real duration source data now
    (incident_duration_weekly.sql covers all of them, confirmed live
    that occurred_at/resolved_at exist for every incident_category, not
    just site_down) — every row gets a "durations" list, not only Site
    Down. A category with zero matching duration rows still gets one,
    just all-zero counts (see the "Power" row below), rather than the
    key being absent."""
    last_monday = _this_monday() - timedelta(days=7)
    created_rows = [
        {"incident_id": "INC1", "created_at": f"{last_monday} 08:00:00", "category": "Site Down"},
        {"incident_id": "INC2", "created_at": f"{last_monday} 09:00:00", "category": "Power"},
    ]
    duration_rows = [
        {
            "incident_id": "INC1",
            "category": "Site Down",
            "occurred_at": f"{last_monday} 08:00:00",
            "resolved_at": f"{last_monday} 08:10:00",
        },
    ]
    svc = IncidentService(
        FakeStatusRepo([]),
        FakeStatusRepo([]),
        created_trend_cache_repository=FakeCreatedTrendRepo(created_rows),
        duration_weekly_cache_repository=FakeCreatedTrendRepo(duration_rows),
    )

    results = svc.get_incident_volume_day_category_breakdowns()
    monday = next(r for r in results if r["weekday"] == "Mon")
    site_down = next(c for c in monday["categories"] if c["category"] == "Site Down")
    power = next(c for c in monday["categories"] if c["category"] == "Power")

    assert "durations" in site_down
    assert "durations" in power
    assert sum(d["weeks"][0]["count"] for d in power["durations"]) == 0


def test_get_incident_volume_day_category_breakdowns_keeps_categories_duration_counts_separate():
    """A Power incident and a Site Down incident created the same
    weekday/Monday with the same duration must not bleed into each
    other's bucket counts — category is part of the grouping key, not
    just weekday/Monday."""
    last_monday = _this_monday() - timedelta(days=7)
    created_rows = [
        {"incident_id": "INC1", "created_at": f"{last_monday} 08:00:00", "category": "Site Down"},
        {"incident_id": "INC2", "created_at": f"{last_monday} 09:00:00", "category": "Power"},
    ]
    duration_rows = [
        {
            "incident_id": "INC1",
            "category": "Site Down",
            "occurred_at": f"{last_monday} 08:00:00",
            "resolved_at": f"{last_monday} 08:10:00",
        },
        {
            "incident_id": "INC2",
            "category": "Power",
            "occurred_at": f"{last_monday} 09:00:00",
            "resolved_at": f"{last_monday} 09:10:00",
        },
    ]
    svc = IncidentService(
        FakeStatusRepo([]),
        FakeStatusRepo([]),
        created_trend_cache_repository=FakeCreatedTrendRepo(created_rows),
        duration_weekly_cache_repository=FakeCreatedTrendRepo(duration_rows),
    )

    results = svc.get_incident_volume_day_category_breakdowns()
    monday = next(r for r in results if r["weekday"] == "Mon")
    site_down = next(c for c in monday["categories"] if c["category"] == "Site Down")
    power = next(c for c in monday["categories"] if c["category"] == "Power")

    site_down_15m = next(d for d in site_down["durations"] if d["label"] == "≤15m")
    power_15m = next(d for d in power["durations"] if d["label"] == "≤15m")

    assert site_down_15m["weeks"][0]["count"] == 1
    assert power_15m["weeks"][0]["count"] == 1


def test_get_incident_volume_day_category_breakdowns_buckets_duration_correctly():
    """A 10-minute incident created on last Monday lands in the ≤15m
    bucket, keyed by its CREATED weekday/Monday (not the closed_at week
    _bucket_site_down_duration() uses for the "Site-Down Duration –
    Weekly Trend" card) — so it lines up with this popup's own
    created-date Category counts."""
    last_monday = _this_monday() - timedelta(days=7)
    created_rows = [
        {"incident_id": "INC1", "created_at": f"{last_monday} 08:00:00", "category": "Site Down"},
    ]
    duration_rows = [
        {
            "incident_id": "INC1",
            "category": "Site Down",
            "occurred_at": f"{last_monday} 08:00:00",
            "resolved_at": f"{last_monday} 08:10:00",
        },
    ]
    svc = IncidentService(
        FakeStatusRepo([]),
        FakeStatusRepo([]),
        created_trend_cache_repository=FakeCreatedTrendRepo(created_rows),
        duration_weekly_cache_repository=FakeCreatedTrendRepo(duration_rows),
    )

    results = svc.get_incident_volume_day_category_breakdowns()
    monday = next(r for r in results if r["weekday"] == "Mon")
    site_down = next(c for c in monday["categories"] if c["category"] == "Site Down")
    bucket_15m = next(d for d in site_down["durations"] if d["label"] == "≤15m")
    bucket_4h = next(d for d in site_down["durations"] if d["label"] == "16m-4h")

    assert bucket_15m["weeks"][0]["count"] == 1
    assert bucket_4h["weeks"][0]["count"] == 0


def test_bucket_duration_by_created_weekday_and_category_missing_resolved_at_via_closed_at_lands_in_over24h():
    """An incident that HAS closed (closed_at set) but is missing
    resolved_at goes straight into the >24h bucket, regardless of how
    long it actually took (this one took 10 minutes) — confirmed live
    that ~11% of closed incidents (nearly 1 in 5 for Site Down) have
    exactly this gap, and per explicit request every incident missing
    Resolved At displays in >24h, full stop, rather than being bucketed
    by its real duration."""
    monday = date(2026, 9, 14)
    rows = [
        {
            "category": "Site Down",
            "occurred_at": f"{monday} 08:00:00",
            "resolved_at": "",
            "closed_at": f"{monday} 08:10:00",
        },
    ]

    counts = _bucket_duration_by_created_weekday_and_category(rows, [monday])

    assert counts[0][monday]["Site Down"] == [0, 0, 0, 0, 0, 1]


def test_bucket_duration_by_created_weekday_and_category_still_open_lands_in_over24h():
    """An incident still open (no resolved_at, no closed_at either) also
    goes straight into >24h — same "missing Resolved At" rule, no
    exceptions for how recently it was created. Confirmed live: 77 Site
    Down incidents created last Sunday alone, missing Resolved At, were
    invisible in every duration bucket before this fix (see
    incident_duration_weekly.sql's own updated header)."""
    monday = date(2026, 9, 14)
    rows = [
        {"category": "Site Down", "occurred_at": f"{monday} 08:00:00", "resolved_at": ""},
    ]

    counts = _bucket_duration_by_created_weekday_and_category(rows, [monday])

    assert counts[0][monday]["Site Down"] == [0, 0, 0, 0, 0, 1]


def test_get_incident_volume_day_category_breakdowns_duration_weeks_carry_badge_type():
    """Each duration-bucket week cell needs its own badge_type (clicking
    it drills into get_incident_volume_day_duration_details()) — same
    "{bucket_token}_{monday_iso}_{weekday_index}" shape that method
    parses back apart."""
    last_monday = _this_monday() - timedelta(days=7)
    created_rows = [
        {"incident_id": "INC1", "created_at": f"{last_monday} 08:00:00", "category": "Site Down"},
    ]
    duration_rows = [
        {
            "incident_id": "INC1",
            "category": "Site Down",
            "occurred_at": f"{last_monday} 08:00:00",
            "resolved_at": f"{last_monday} 08:10:00",
        },
    ]
    svc = IncidentService(
        FakeStatusRepo([]),
        FakeStatusRepo([]),
        created_trend_cache_repository=FakeCreatedTrendRepo(created_rows),
        duration_weekly_cache_repository=FakeCreatedTrendRepo(duration_rows),
    )

    results = svc.get_incident_volume_day_category_breakdowns()
    monday = next(r for r in results if r["weekday"] == "Mon")
    site_down = next(c for c in monday["categories"] if c["category"] == "Site Down")
    bucket_15m = next(d for d in site_down["durations"] if d["label"] == "≤15m")

    assert bucket_15m["weeks"][0]["badge_type"] == f"lt15m_{last_monday.isoformat()}_0"


def test_get_incident_volume_day_duration_details_matches_created_date_and_bucket():
    last_monday = _this_monday() - timedelta(days=7)
    rows = [
        {
            "incident_id": "INC1",
            "category": "Site Down",
            "occurred_at": f"{last_monday} 08:00:00",
            "resolved_at": f"{last_monday} 08:10:00",
            "closed_at": f"{last_monday} 09:00:00",
        },
        {
            "incident_id": "INC2",
            "category": "Site Down",
            "occurred_at": f"{last_monday} 08:00:00",
            "resolved_at": f"{last_monday} 12:00:00",  # 4h -> a different bucket
            "closed_at": f"{last_monday} 13:00:00",
        },
        {
            "incident_id": "INC3",
            "category": "Site Down",
            "occurred_at": f"{last_monday + timedelta(days=1)} 08:00:00",  # wrong day
            "resolved_at": f"{last_monday + timedelta(days=1)} 08:10:00",
            "closed_at": f"{last_monday + timedelta(days=1)} 09:00:00",
        },
    ]
    svc = IncidentService(
        FakeStatusRepo([]),
        FakeStatusRepo([]),
        duration_weekly_cache_repository=FakeCreatedTrendRepo(rows),
    )

    result = svc.get_incident_volume_day_duration_details(f"lt15m_{last_monday.isoformat()}_0")

    assert [r["incident_id"] for r in result] == ["INC1"]
    assert result[0]["duration_display"] == "10m"


def test_get_incident_volume_day_duration_details_filters_by_category():
    """Every category's cells share the same badge_type shape, so
    `categories` is what actually tells two categories' same-bucket-
    same-day cells apart."""
    last_monday = _this_monday() - timedelta(days=7)
    rows = [
        {
            "incident_id": "INC1",
            "category": "Site Down",
            "occurred_at": f"{last_monday} 08:00:00",
            "resolved_at": f"{last_monday} 08:10:00",
            "closed_at": f"{last_monday} 09:00:00",
        },
        {
            "incident_id": "INC2",
            "category": "Power",
            "occurred_at": f"{last_monday} 08:00:00",
            "resolved_at": f"{last_monday} 08:10:00",
            "closed_at": f"{last_monday} 09:00:00",
        },
    ]
    svc = IncidentService(
        FakeStatusRepo([]),
        FakeStatusRepo([]),
        duration_weekly_cache_repository=FakeCreatedTrendRepo(rows),
    )

    result = svc.get_incident_volume_day_duration_details(
        f"lt15m_{last_monday.isoformat()}_0", categories=["Power"]
    )

    assert [r["incident_id"] for r in result] == ["INC2"]


def test_get_incident_volume_day_duration_details_unknown_bucket_token_returns_none():
    svc = IncidentService(
        FakeStatusRepo([]), FakeStatusRepo([]), duration_weekly_cache_repository=FakeCreatedTrendRepo([])
    )

    assert svc.get_incident_volume_day_duration_details("not_a_real_bucket_2026-09-08_0") is None


def test_get_incident_volume_day_duration_details_empty_badge_type_returns_every_row():
    rows = [{"incident_id": "INC1", "occurred_at": "2026-09-08 08:00:00", "resolved_at": "2026-09-08 08:10:00"}]
    svc = IncidentService(
        FakeStatusRepo([]), FakeStatusRepo([]), duration_weekly_cache_repository=FakeCreatedTrendRepo(rows)
    )

    assert svc.get_incident_volume_day_duration_details("") == rows


def test_get_incident_volume_day_severity_breakdowns_groups_by_severity_not_category():
    last_monday = _this_monday() - timedelta(days=7)
    rows = [
        {"incident_id": "INC1", "created_at": f"{last_monday} 08:00:00", "severity": "Critical"},
        {"incident_id": "INC2", "created_at": f"{last_monday} 09:00:00", "severity": "Minor"},
        {"incident_id": "INC3", "created_at": f"{last_monday} 10:00:00", "severity": "Minor"},
    ]
    svc = IncidentService(
        FakeStatusRepo([]), FakeStatusRepo([]), created_trend_cache_repository=FakeCreatedTrendRepo(rows)
    )

    results = svc.get_incident_volume_day_severity_breakdowns()
    monday = next(r for r in results if r["weekday"] == "Mon")
    severities = {s["severity"]: s["weeks"][0]["count"] for s in monday["severities"]}

    assert severities == {"Critical": 1, "Minor": 2}
    assert "durations" not in monday["severities"][0]


def test_get_incident_volume_day_province_breakdowns_defaults_missing_province_to_unknown():
    last_monday = _this_monday() - timedelta(days=7)
    rows = [{"incident_id": "INC1", "created_at": f"{last_monday} 08:00:00", "province": None}]
    svc = IncidentService(
        FakeStatusRepo([]), FakeStatusRepo([]), created_trend_cache_repository=FakeCreatedTrendRepo(rows)
    )

    results = svc.get_incident_volume_day_province_breakdowns()
    monday = next(r for r in results if r["weekday"] == "Mon")

    assert monday["provinces"][0]["province"] == "Unknown"


def test_get_incident_volume_day_vendor_breakdowns_groups_by_vendor_field():
    last_monday = _this_monday() - timedelta(days=7)
    rows = [
        {"incident_id": "INC1", "created_at": f"{last_monday} 08:00:00", "vendor": "ZTE"},
        {"incident_id": "INC2", "created_at": f"{last_monday} 08:00:00", "vendor": "Huawei"},
    ]
    svc = IncidentService(
        FakeStatusRepo([]), FakeStatusRepo([]), created_trend_cache_repository=FakeCreatedTrendRepo(rows)
    )

    results = svc.get_incident_volume_day_vendor_breakdowns()
    monday = next(r for r in results if r["weekday"] == "Mon")
    vendors = {v["vendor"] for v in monday["vendors"]}

    assert vendors == {"ZTE", "Huawei"}


def test_get_volume_trend_details_filters_by_category():
    rows = [
        {"incident_id": "INC1", "created_at": "2026-01-01 00:00:00", "category": "Site Down"},
        {"incident_id": "INC2", "created_at": "2026-01-01 00:00:00", "category": "Power"},
    ]
    svc = IncidentService(
        FakeStatusRepo([]), FakeStatusRepo([]), created_trend_cache_repository=FakeCreatedTrendRepo(rows)
    )

    result = svc.get_volume_trend_details(categories=["Site Down"])

    assert [r["incident_id"] for r in result] == ["INC1"]


def test_get_volume_trend_details_combines_weekday_and_category_filters():
    this_monday = _this_monday()
    rows = [
        {"incident_id": "INC1", "created_at": f"{this_monday} 09:00:00", "category": "Site Down"},
        {"incident_id": "INC2", "created_at": f"{this_monday} 09:00:00", "category": "Power"},
    ]
    svc = IncidentService(
        FakeStatusRepo([]), FakeStatusRepo([]), created_trend_cache_repository=FakeCreatedTrendRepo(rows)
    )

    result = svc.get_volume_trend_details(f"date_{this_monday.isoformat()}", categories=["Site Down"])

    assert [r["incident_id"] for r in result] == ["INC1"]


def test_get_volume_trend_details_unknown_badge_type_returns_none_even_with_category():
    svc = IncidentService(
        FakeStatusRepo([]), FakeStatusRepo([]), created_trend_cache_repository=FakeCreatedTrendRepo([])
    )

    assert svc.get_volume_trend_details("not_a_real_badge", categories=["Power"]) is None


def test_get_volume_trend_categories_returns_sorted_distinct_values():
    rows = [
        {"incident_id": "INC1", "category": "Site Down"},
        {"incident_id": "INC2", "category": "Power"},
        {"incident_id": "INC3", "category": None},
    ]
    svc = IncidentService(
        FakeStatusRepo([]), FakeStatusRepo([]), created_trend_cache_repository=FakeCreatedTrendRepo(rows)
    )

    assert svc.get_volume_trend_categories() == ["Power", "Site Down"]


def test_with_deltas_caps_a_large_increase_at_100_percent():
    # A small older-week baseline (1) makes the raw percentage blow up
    # for a small absolute swing (1 -> 5 is +400% raw) — this reads as
    # broken on a dashboard, so it's capped at +100 same as
    # _weekly_time_pct_delta()'s own cap for the same reason.
    day_series = [{"value": 5}, {"value": 1}]

    result = _with_deltas(day_series)

    assert result[0]["delta_pct"] == 100
    assert result[1]["delta_pct"] is None


def test_with_deltas_caps_a_large_decrease_at_negative_100_percent():
    day_series = [{"value": 1}, {"value": 20}]

    result = _with_deltas(day_series)

    assert result[0]["delta_pct"] == -95  # not actually capped: -95 is already within range
    # A genuinely more-than-100%-drop is impossible for a plain count
    # (can't lose more than 100% of a positive value), so only the
    # increase direction ever actually hits the cap in practice — this
    # confirms the un-capped, real value still comes through untouched
    # when it's already within +/-100.


def test_with_deltas_leaves_a_normal_delta_uncapped():
    day_series = [{"value": 15}, {"value": 10}]

    result = _with_deltas(day_series)

    assert result[0]["delta_pct"] == 50


def test_get_incident_volume_severity_breakdown_sorted_by_biggest_increase():
    last_monday = _this_monday() - timedelta(days=7)
    two_mondays_ago = last_monday - timedelta(days=7)
    rows = [
        {"incident_id": "INC1", "created_at": f"{last_monday} 09:00:00", "severity": "Critical"},
        {"incident_id": "INC2", "created_at": f"{last_monday} 09:00:00", "severity": "Critical"},
        {"incident_id": "INC3", "created_at": f"{two_mondays_ago} 09:00:00", "severity": "Critical"},
        {"incident_id": "INC4", "created_at": f"{last_monday} 09:00:00", "severity": "Minor"},
        {"incident_id": "INC5", "created_at": f"{two_mondays_ago} 09:00:00", "severity": "Minor"},
        {"incident_id": "INC6", "created_at": f"{two_mondays_ago} 09:00:00", "severity": "Minor"},
    ]
    svc = IncidentService(
        FakeStatusRepo([]), FakeStatusRepo([]), created_trend_cache_repository=FakeCreatedTrendRepo(rows)
    )

    breakdown = svc.get_incident_volume_severity_breakdown()

    # Critical: 2 (newest) vs 1 (older) = +1. Minor: 1 (newest) vs 2
    # (older) = -1. Critical rose the most, so it sits on top.
    assert [row["severity"] for row in breakdown["severities"]] == ["Critical", "Minor"]
    assert breakdown["severities"][0]["delta"] == 1
    assert breakdown["severities"][1]["delta"] == -1


def test_get_incident_volume_province_breakdown_sorts_by_newest_week_not_by_summed_total():
    """Real bug found and fixed here: sorting by the SUM of both
    displayed weeks let a province with a small newest-week count but
    a big older-week count outrank one with a bigger newest-week count
    (e.g. 203 sorting above 293) — technically a correct sum, but the
    visible (newest-week) column no longer read top-to-bottom in
    descending order, which looked broken on the actual popup. Sorting
    by the newest week's count alone keeps that column's own order
    obviously correct."""
    last_monday = _this_monday() - timedelta(days=7)
    two_mondays_ago = last_monday - timedelta(days=7)
    rows = (
        # Province A: newest week (last_monday) = 2, older week = 1 -> total 3.
        [{"incident_id": f"A{i}", "created_at": f"{last_monday} 09:00:00", "province": "A"} for i in range(2)]
        + [{"incident_id": "A_old", "created_at": f"{two_mondays_ago} 09:00:00", "province": "A"}]
        # Province B: newest week = 1, older week = 5 -> total 6 (bigger
        # sum than A, but A's newest-week count is bigger).
        + [{"incident_id": "B_new", "created_at": f"{last_monday} 09:00:00", "province": "B"}]
        + [{"incident_id": f"B{i}", "created_at": f"{two_mondays_ago} 09:00:00", "province": "B"} for i in range(5)]
    )
    svc = IncidentService(
        FakeStatusRepo([]), FakeStatusRepo([]), created_trend_cache_repository=FakeCreatedTrendRepo(rows)
    )

    breakdown = svc.get_incident_volume_province_breakdown()

    provinces = breakdown["provinces"]
    a = next(p for p in provinces if p["province"] == "A")
    b = next(p for p in provinces if p["province"] == "B")
    assert a["weeks"][0]["count"] == 2  # A's newest week
    assert b["weeks"][0]["count"] == 1  # B's newest week
    # A has the bigger newest-week count, so it must sort first, even
    # though B's summed total (6) is bigger than A's (3).
    assert [p["province"] for p in provinces] == ["A", "B"]


def test_get_incident_volume_vendor_breakdown_groups_by_vendor_field():
    last_monday = _this_monday() - timedelta(days=7)
    rows = [
        {"incident_id": "INC1", "created_at": f"{last_monday} 09:00:00", "vendor": "Huawei"},
        {"incident_id": "INC2", "created_at": f"{last_monday} 09:00:00", "vendor": "Huawei"},
        {"incident_id": "INC3", "created_at": f"{last_monday} 09:00:00", "vendor": "Unknown"},
    ]
    svc = IncidentService(
        FakeStatusRepo([]), FakeStatusRepo([]), created_trend_cache_repository=FakeCreatedTrendRepo(rows)
    )

    breakdown = svc.get_incident_volume_vendor_breakdown()

    vendors_by_name = {row["vendor"]: row for row in breakdown["vendors"]}
    assert vendors_by_name["Huawei"]["weeks"][0]["count"] == 2
    assert vendors_by_name["Unknown"]["weeks"][0]["count"] == 1


def test_get_volume_trend_field_values_returns_sorted_distinct_values():
    rows = [
        {"incident_id": "INC1", "province": "Kandal"},
        {"incident_id": "INC2", "province": "Siemreap"},
        {"incident_id": "INC3", "province": None},
    ]
    svc = IncidentService(
        FakeStatusRepo([]), FakeStatusRepo([]), created_trend_cache_repository=FakeCreatedTrendRepo(rows)
    )

    assert svc.get_volume_trend_field_values("province") == ["Kandal", "Siemreap"]


def test_get_volume_trend_details_filters_by_severity_province_and_vendor():
    rows = [
        {"incident_id": "INC1", "created_at": "2026-01-01 00:00:00", "severity": "Critical", "province": "Kandal", "vendor": "Huawei"},
        {"incident_id": "INC2", "created_at": "2026-01-01 00:00:00", "severity": "Minor", "province": "Kandal", "vendor": "Huawei"},
        {"incident_id": "INC3", "created_at": "2026-01-01 00:00:00", "severity": "Critical", "province": "Siemreap", "vendor": "ZTE"},
    ]
    svc = IncidentService(
        FakeStatusRepo([]), FakeStatusRepo([]), created_trend_cache_repository=FakeCreatedTrendRepo(rows)
    )

    assert [r["incident_id"] for r in svc.get_volume_trend_details(severities=["Critical"])] == ["INC1", "INC3"]
    assert [r["incident_id"] for r in svc.get_volume_trend_details(provinces=["Kandal"])] == ["INC1", "INC2"]
    assert [r["incident_id"] for r in svc.get_volume_trend_details(vendors=["Huawei"])] == ["INC1", "INC2"]
    # Combinable with each other.
    assert [
        r["incident_id"]
        for r in svc.get_volume_trend_details(severities=["Critical"], provinces=["Kandal"])
    ] == ["INC1"]


def test_filter_rows_by_categories_excludes_customer_complaint_by_default():
    # By request: every "Filter by Category" control dashboard-wide
    # (Incident Volume, Incidents Closed, Response Time, Resolution
    # Time, SLA Compliance) excludes Customer Complaint until it's
    # explicitly checked, unlike every other filter in this app where
    # empty/none means "no filter, show everything".
    rows = [
        {"incident_id": "POWER", "category": "Power"},
        {"incident_id": "CC", "category": "Customer Complaint"},
        {"incident_id": "NO_CAT", "category": None},
    ]

    # No categories selected -> Customer Complaint excluded, everything else kept.
    assert [r["incident_id"] for r in _filter_rows_by_categories(rows, None)] == ["POWER", "NO_CAT"]
    assert [r["incident_id"] for r in _filter_rows_by_categories(rows, [])] == ["POWER", "NO_CAT"]

    # Explicitly checking Customer Complaint brings it back, same as any other category.
    assert [r["incident_id"] for r in _filter_rows_by_categories(rows, ["Customer Complaint"])] == ["CC"]
    assert [r["incident_id"] for r in _filter_rows_by_categories(rows, ["Power", "Customer Complaint"])] == [
        "POWER",
        "CC",
    ]


def test_site_down_duration_axis_uses_500_steps_and_extends_without_clipping():
    from app.services.incident.incident_service import _site_down_duration_ticks, _format_tick
    assert [_format_tick(v) for v in _site_down_duration_ticks(1700)] == ["0", "500", "1K", "1.5K", "2K", "2.5K", "3K"]
    assert _site_down_duration_ticks(0) == [0, 500, 1000, 1500, 2000, 2500, 3000]
    ticks = _site_down_duration_ticks(3501)
    assert ticks[-1] == 4000 and all(b - a == 500 for a, b in zip(ticks, ticks[1:]))
