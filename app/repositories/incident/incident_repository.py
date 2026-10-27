"""Data access for the Incident table (object_322) on PostgreSQL."""

from app.database.connection import run_query


class IncidentRepository:
    def fetch_by_status(self):
        """Full joined drilldown detail for every Incident currently
        'new' or 'in_progress' — see incident_by_status.sql."""
        return run_query("incident_by_status", "incident_by_status")

    def fetch_site_down(self):
        """Every Site Down incident not yet Closed whose alarm hasn't
        cleared — see incident_site_down.sql. Used both live (Telegram
        alert) and cached (Incident Site Down card)."""
        return run_query("incident_site_down", "incident_site_down")

    def fetch_vip_incident_status(self, mssql_vip_site_codes=()):
        """Every not-yet-Closed Incident (including Resolved) at a site
        VIP/VVIP per Postgres's own site_strategic_type OR per MSSQL's
        TBL_SITE.SITE_STRATEGIC (mssql_vip_site_codes — see
        vip_site_cache, kept more current than Postgres's own flag for
        site data specifically) — used only by VipAlarmService's
        enrichment. An empty list is safe here (ANY() over an empty
        array just matches nothing, verified directly against Postgres),
        so callers don't need to special-case "no MSSQL codes yet"."""
        return run_query(
            "vip_incident_status",
            "vip_incident_status",
            mssql_vip_site_codes=list(mssql_vip_site_codes),
        )

    def fetch_closed_trend(self, since):
        """One row per Incident closed on/after `since` (the oldest
        Monday _available_weeks() can offer — see incident_sync_
        service.py's _oldest_available_monday()), its own closed_at,
        not a WO's resolved_at — "Incidents Closed" card. Pair with
        fetch_closed_trend_by_ids() for detail."""
        return run_query("incident_closed_trend", "incident_closed_trend", since=since)

    def fetch_closed_trend_by_ids(self, incident_ids):
        """Category/site/location detail for a batch of Incident
        numeric ids — step 2 for fetch_closed_trend()."""
        if not incident_ids:
            return []
        return run_query(
            "incident_closed_trend_by_ids",
            "incident_closed_trend_by_ids",
            incident_ids=list(incident_ids),
        )

    def fetch_site_down_restored_by_ids(self, incident_ids):
        """Restored timestamp + Root Cause for a batch of (text)
        incident_id strings already down-alerted and pending a
        restore-confirmation — Site Down 24h alert's own Stage 2. Only
        returns the ones that have actually resolved by now; see
        incident_site_down_restored_by_ids.sql's own header."""
        if not incident_ids:
            return []
        return run_query(
            "incident_site_down_restored_by_ids",
            "incident_site_down_restored_by_ids",
            incident_ids=list(incident_ids),
        )

    def fetch_created_trend(self, since):
        """One row per Incident created on/after `since` (the oldest
        Monday _available_weeks() can offer), any status — "Incident
        Volume" card. Pair with fetch_created_trend_by_ids()."""
        return run_query("incident_created_trend", "incident_created_trend", since=since)

    def fetch_created_trend_by_ids(self, incident_ids):
        """Status/category/site/location detail for a batch of Incident
        numeric ids — step 2 for fetch_created_trend()."""
        if not incident_ids:
            return []
        return run_query(
            "incident_created_trend_by_ids",
            "incident_created_trend_by_ids",
            incident_ids=list(incident_ids),
        )

    def fetch_site_down_root_cause(self, since):
        """Every incident with issue_occurred_at on/after `since` (the
        oldest Monday _available_weeks() can offer), not pre-filtered
        to Site Down — see incident_site_down_root_cause.sql for why —
        with the real Root Cause Category Streamline assigns via the
        object_10 join. incident_sync_service.py's
        sync_site_down_root_cause() filters to Site Down in Python
        afterward."""
        return run_query(
            "incident_site_down_root_cause", "incident_site_down_root_cause", since=since
        )

    def fetch_site_down_duration_weekly(self, since):
        """Closed Site Down incidents with closed_at on/after `since`
        (the oldest Monday _available_weeks() can offer — see
        incident_sync_service.py's sync_site_down_duration_weekly()),
        with both issue_occurred_at and resolved_at so duration can be
        bucketed per week — see incident_site_down_duration_weekly.sql.
        Pair with fetch_site_down_duration_by_ids() for Site Name/Code."""
        return run_query(
            "incident_site_down_duration_weekly", "incident_site_down_duration_weekly", since=since
        )

    def fetch_site_down_duration_by_ids(self, incident_ids):
        """Site Name/Code detail for a batch of Incident numeric ids —
        step 2 for fetch_site_down_duration_weekly(). A multi-site
        incident returns one row per site here."""
        if not incident_ids:
            return []
        return run_query(
            "incident_site_down_duration_weekly_by_ids",
            "incident_site_down_duration_weekly_by_ids",
            incident_ids=list(incident_ids),
        )

    def fetch_duration_weekly(self, since):
        """Closed (or still-open) incidents on/after `since` (the
        oldest Monday _available_weeks() can offer), every category,
        with both issue_occurred_at and resolved_at so duration can be
        bucketed per weekday — see incident_duration_weekly.sql. Pair
        with fetch_site_down_duration_by_ids() for Site Name/Code (that
        step-2 query isn't scoped to any one category, safe to reuse
        as-is here)."""
        return run_query("incident_duration_weekly", "incident_duration_weekly", since=since)

    def fetch_response_time_weekly(self):
        """Response Time — Weekly Trend (ISO weeks, last 4 weeks),
        sourced directly from object_322, no join — see
        incident_response_time_weekly.sql."""
        return run_query("incident_response_time_weekly", "incident_response_time_weekly")

    def fetch_response_time_details(self):
        """Per-incident rows behind Response Time's duration-bucket
        breakdown — same filter/window as fetch_response_time_weekly()
        but one row per incident, no GROUP BY — see
        incident_response_time_details.sql."""
        return run_query("incident_response_time_details", "incident_response_time_details")

    def fetch_resolution_time_weekly(self):
        """Resolution Time — Weekly Trend (ISO weeks, last 4 weeks),
        sourced directly from object_322, no join — see
        incident_resolution_time_weekly.sql."""
        return run_query("incident_resolution_time_weekly", "incident_resolution_time_weekly")

    def fetch_resolution_time_details(self):
        """Per-incident rows behind Resolution Time's duration-bucket
        breakdown — same filter/window as fetch_resolution_time_weekly()
        but one row per incident, no GROUP BY — see
        incident_resolution_time_details.sql."""
        return run_query("incident_resolution_time_details", "incident_resolution_time_details")

    def fetch_sla_compliance_weekly(self):
        """SLA Compliance — Weekly Trends (ISO weeks, last 4 weeks),
        sourced directly from object_322, no join — see
        incident_sla_compliance_weekly.sql."""
        return run_query("incident_sla_compliance_weekly", "incident_sla_compliance_weekly")

    def fetch_sla_compliance_details(self):
        """Per-incident rows behind the SLA Compliance card's per-week
        popup — same filter/window as fetch_sla_compliance_weekly() but
        one row per incident, no GROUP BY — see
        incident_sla_compliance_details.sql."""
        return run_query("incident_sla_compliance_details", "incident_sla_compliance_details")

    def fetch_wo_by_incident_ids(self, incident_ids):
        """Every INC-WO belonging to a batch of incident numeric ids,
        in one round-trip. Returns [] without a Postgres call if empty."""
        if not incident_ids:
            return []
        return run_query(
            "inc_wo_by_incident_ids", "inc_wo_by_incident_ids", incident_ids=list(incident_ids)
        )

    def fetch_worklog_by_ids(self, incident_ids):
        """Free-text Worklog comments (object_362) for a batch of
        incident numeric ids — one HALF of Streamline's own "Worklog"
        tab; pair with fetch_audit_log_by_ids() for the other half (its
        system field-change entries) — see incident_worklog_by_ids.sql."""
        if not incident_ids:
            return []
        return run_query(
            "incident_worklog_by_ids", "incident_worklog_by_ids", incident_ids=list(incident_ids)
        )

    def fetch_audit_log_by_ids(self, incident_ids):
        """System field-change entries (object_323, "Field 'Status'
        changed from 'New' to 'In Progress'") for a batch of incident
        numeric ids — the other HALF of Streamline's own "Worklog" tab;
        pair with fetch_worklog_by_ids() for the free-text comments —
        see incident_audit_log_by_ids.sql."""
        if not incident_ids:
            return []
        return run_query(
            "incident_audit_log_by_ids", "incident_audit_log_by_ids", incident_ids=list(incident_ids)
        )

    def fetch_combined_worklog_by_ids(self, incident_ids):
        """Both halves of Streamline's own "Worklog" tab (free-text
        comments + system field-change entries) merged into ONE
        timeline, newest first — matching exactly what Streamline
        itself shows (confirmed live against a real incident: 4 comment
        rows + 3 field-change rows = the same 7 entries, same order,
        seen on screen). Each entry gets a plain "text" line so the
        caller/template doesn't need to know which of the two sources
        it came from — a field-change entry's text is built the same
        "Field 'X' changed from 'Y' to 'Z'" way Streamline's own UI
        phrases it, with a bare value shown as "Null" to match."""
        comments = [
            {
                "incident_numeric_id": r["Incident Numeric ID"],
                "incident_id": r["Incident ID"],
                "text": r["Worklog"],
                "created_at": r["Created At"],
                "created_by": r["Created By"],
            }
            for r in self.fetch_worklog_by_ids(incident_ids)
        ]
        field_changes = [
            {
                "incident_numeric_id": r["Incident Numeric ID"],
                "incident_id": r["Incident ID"],
                "text": (
                    f"Field '{r['Field']}' changed from "
                    f"'{r['From'] if r['From'] not in (None, '') else 'Null'}' to "
                    f"'{r['To'] if r['To'] not in (None, '') else 'Null'}'"
                ),
                "created_at": r["Created At"],
                "created_by": r["Created By"],
            }
            for r in self.fetch_audit_log_by_ids(incident_ids)
        ]
        return sorted(comments + field_changes, key=lambda e: e["created_at"], reverse=True)
