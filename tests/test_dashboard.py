def test_index_returns_200(client):
    response = client.get("/")
    assert response.status_code == 200


def test_drilldown_returns_200(client):
    response = client.get(
        "/drilldown?title=VVIP+Door+Alarm&label=Door+Alarm&value=0&scope=VVIP+Site"
    )
    assert response.status_code == 200
    assert b"No VIP/VVIP site alarms found" in response.data


def test_dc_low_high_drilldown_returns_200(client):
    response = client.get(
        "/drilldown?title=DC+Low%2FHigh&label=DC+Low%2FHigh&value=0&scope=DC+Low%2FHigh"
    )
    assert response.status_code == 200
    assert b"No DC Low/High found" in response.data


def test_incident_drilldown_returns_200(client):
    """Renders incidents.html — the "Incident" card's drilldown, backed by
    incident_by_status (now one row per (incident, site) pair, see
    tests/test_cache_migration.py). Empty here just proves the template
    still renders cleanly; the per-site fan-out itself is covered at the
    cache/repository level."""
    response = client.get("/drilldown?title=Incident&label=Incident&value=0&scope=Incident")
    assert response.status_code == 200
    assert b"No incidents found" in response.data


def _seed_inc_wo_rows(app, count):
    from app.repositories.incwo.incwo_status_cache_repository import IncWoStatusCacheRepository

    with app.app_context():
        rows = [
            {
                "incident_id": f"INC{i}",
                "incident_numeric_id": i,
                "incident_status": "New",
                "wo_id": f"WO{i}",
                "wo_numeric_id": i,
                "wo_created_at": f"2026-01-{(i % 28) + 1:02d} 00:00:00",
                "wo_status": "New",
                "resolved_at": "",
                "incident_category": "Site Down",
                "site_name": "Site A",
                "site_code": "S1",
                "overdue": "No",
                "support_level": "",
                "responsible_team": "",
                "fault_description": "",
                "resolution": "",
                "nms": "",
                "hub_site": "",
                "site_grade": "",
                "province": "",
                "district": "",
                "commune": "",
            }
            for i in range(count)
        ]
        IncWoStatusCacheRepository().replace_all("inc_wo_by_status", rows)


def test_inc_wo_drilldown_caps_unfiltered_rows(client, app):
    """The plain "View INC-WO" link (no badge type) used to render every
    non-closed WO in one giant HTML table — at 2,400+ real rows this made
    the page feel stuck. Capped to the newest 500 for the HTML render
    only (see _SCOPE_HANDLERS["INC-WO"]["row_cap"])."""
    _seed_inc_wo_rows(app, 600)

    response = client.get("/drilldown?title=INC-WO&label=INC-WO&value=0&scope=INC-WO")

    assert response.status_code == 200
    assert response.data.count(b"<tr>") == 501  # 1 header row + 500 capped data rows
    assert b"Showing the newest 500 of 600 rows" in response.data


def test_inc_wo_drilldown_no_notice_when_under_cap(client, app):
    _seed_inc_wo_rows(app, 10)

    response = client.get("/drilldown?title=INC-WO&label=INC-WO&value=0&scope=INC-WO")

    assert response.status_code == 200
    assert response.data.count(b"<tr>") == 11  # 1 header row + 10 data rows
    assert b"Showing the newest" not in response.data


def test_inc_wo_csv_export_is_not_capped(client, app):
    """CSV export is a deliberate full data-dump use case, not a rendered
    HTML table a browser has to lay out — the row cap must not apply
    there, only to the HTML view."""
    _seed_inc_wo_rows(app, 600)

    response = client.get("/drilldown/download?scope=INC-WO&type=")

    assert response.status_code == 200
    # header row + 600 data rows, one CSV line each
    assert len(response.data.decode().strip().splitlines()) == 601


def _seed_tct_alarm_rows(app, alarms):
    from app.repositories.alarm.alarm_cache_repository import AlarmCacheRepository

    with app.app_context():
        rows = [
            {
                "id": f"ID{i}",
                "alarm": alarm,
                "alarm_name": f"TCT_{alarm}",
                "device_name": f"DEV{i}",
                "ip_address": "",
                "pop_name": "",
                "pop_code": "",
                "province": "",
                "pro_owner": "",
                "down_time": "2026-09-01 00:00:00",
                "restored_time": "",
                "root_cause": "",
                "rtid": "",
                "interface": "",
                "source_group": "",
                "additional_info": "",
                "note": "",
                "ack": "",
                "ab": "",
                "mb": "",
                "md": "",
            }
            for i, alarm in enumerate(alarms)
        ]
        AlarmCacheRepository().replace_all("tct_alarm_cache", rows)


def test_tct_congestion_drilldown_includes_bandwidth_rows_too(client, app):
    """The TCT card's Congestion badge count is bandwidth + congestion
    merged (see AlarmService.get_tct_counts()) — its drilldown link sends
    type=bandwidth,congestion so the table it opens actually shows every
    row the badge number counted, not just the ones literally named
    'congestion'."""
    _seed_tct_alarm_rows(app, ["bandwidth", "bandwidth", "congestion", "bgp"])

    response = client.get(
        "/drilldown?title=Congestion&label=Congestion&value=0"
        "&scope=IP+Telcotech%2FCellcard&type=bandwidth%2Ccongestion"
    )

    assert response.status_code == 200
    assert response.data.count(b"<tr>") == 4  # 1 header + 3 bandwidth/congestion rows, not bgp


def _seed_response_time_weekly_rows(app, week_counts):
    """week_counts: {iso_week: incident_count}, one row per week."""
    from app.repositories.incident.incident_response_time_weekly_cache_repository import (
        IncidentResponseTimeWeeklyCacheRepository,
    )

    with app.app_context():
        rows = [
            {
                "iso_week": iso,
                "category": "Power",
                "incident_count": count,
                "min_minutes": 1.0,
                "avg_minutes": 5.0,
                "max_minutes": 10.0,
            }
            for iso, count in week_counts.items()
        ]
        IncidentResponseTimeWeeklyCacheRepository().replace_all(
            "incident_response_time_weekly", rows
        )


def test_dashboard_does_not_crash_when_only_one_week_selected_for_compare(client, app):
    """Checking just one "Compare Weeks" box used to crash the whole
    page with IndexError (_build_weekly_time_context()'s
    selected_rows[-2] on a length-1 list) — Response Time/Resolution
    Time both share that helper, so a single-week pick on either one
    must render 200, not 500, with no "vs last week" delta shown."""
    _seed_response_time_weekly_rows(app, {"2026-W35": 10, "2026-W36": 12, "2026-W37": 8})

    response = client.get("/?response_time_week=2026-W36")

    assert response.status_code == 200




def test_compatible_security_headers_and_configurable_source_url(client, app):
    app.config["STREAMLINE_BASE_URL"] = "https://source.example.test"
    response = client.get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert "frame-ancestors 'self'" in response.headers["Content-Security-Policy"]
    assert 'data-streamline-base="https://source.example.test"' in response.get_data(as_text=True)


def test_invalid_worklog_bucket_is_not_found(client):
    assert client.get("/dashboard/worklog/not-a-bucket").status_code == 404


def test_empty_charts_use_shared_svg_instead_of_zero_plots(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    performance_html = client.get("/performance-cards").get_data(as_text=True)
    assert (html + performance_html).count('class="chart-empty-state"') >= 8
    assert 'images/no-data-available.svg' in html
    assert 'class="campaign-chart-row"' not in html
    assert 'class="sales-chart-row"' not in html
    congestion = client.get("/congestion")
    assert congestion.status_code == 200
    assert 'class="chart-empty-state"' in congestion.get_data(as_text=True)
