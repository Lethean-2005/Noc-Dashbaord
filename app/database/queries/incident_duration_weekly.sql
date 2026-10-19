-- ==============================================================
-- "By Category — <Weekday>" popup's duration breakdown (Incident
-- Volume card, graph_cards.html) — every category, not just Site Down.
-- Step 1 of 2, same split as incident_site_down_duration_weekly.sql
-- (see incident_site_down_duration_weekly_by_ids.sql for step 2, which
-- resolves Site Name/Code and is reused as-is here — it's already
-- generic, not filtered to any one category).
--
-- Confirmed live against object_322 that issue_occurred_at/resolved_at
-- are populated for every incident_category, not just site_down —
-- incident_site_down_duration_weekly.sql's own category filter was
-- scoped narrowly for that one card's specific purpose, not because
-- other categories lack these fields.
--
-- Deliberately no JOIN here — same "conflict with recovery" reasoning
-- as incident_site_down_duration_weekly.sql (a full 30-day scan of
-- object_322 is already this query's whole cost; adding the
-- LATERAL-UNNEST + object_160/308 join directly here would repeat the
-- same replication-race problem that query's header describes).
--
-- Keyed off closed_at's presence, not status = 'closed' text or
-- resolved_at IS NOT NULL — confirmed live that ~11% of closed
-- incidents (2,325 of 21,032 in a 30-day window; nearly 1 in 5 for
-- Site Down specifically) have closed_at set but resolved_at left
-- NULL (closed through a workflow path that skips it), which the old
-- "resolved_at IS NOT NULL" filter silently threw away entirely —
-- these incidents used to be silently thrown away entirely by the old
-- "resolved_at IS NOT NULL" filter. incident_service.py's own bucketing
-- (Python side) buckets by real duration when Resolved At is present,
-- and — per explicit request — puts every row missing Resolved At
-- straight into the >24h bucket unconditionally, whether it's closed
-- via Closed At or still fully open, with no real-duration calculation
-- attempted for that case at all.
--
-- The two branches below are simply "has closed" (any closed_at in
-- the last 30 days, whichever of Resolved/Closed At Python ends up
-- using) vs "hasn't closed yet" (no closed_at at all, scoped by
-- issue_occurred_at instead since there's no closed_at to filter on).
--
-- :since (bound below, not a literal INTERVAL) is the oldest Monday
-- _available_weeks() can ever offer in "Compare Weeks" checkboxes
-- dashboard-wide — see incident_closed_trend.sql's own comment (and
-- incident_sync_service.py's _oldest_available_monday()) for why a
-- rolling day-count cutoff isn't safe here. Same :since value bound
-- into both branches below.
-- ==============================================================

-- name: incident_duration_weekly
SELECT
  inc.incident_id AS "Incident ID",
  inc.id AS "Incident Numeric ID",
  CASE inc.incident_category
    WHEN 'bss_hardware' THEN 'BSS Hardware'
    WHEN 'bss_software' THEN 'BSS Software'
    WHEN 'oss_platform' THEN 'OSS Platform'
    WHEN 'ip_core' THEN 'IP Core'
    WHEN 'cs_core' THEN 'CS Core'
    WHEN 'ps_core' THEN 'PS Core'
    ELSE INITCAP(REPLACE(inc.incident_category, '_', ' '))
  END AS "Category",
  inc.issue_occurred_at AS "Occurred At",
  inc.resolved_at AS "Resolved At",
  inc.closed_at AS "Closed At"
FROM object_322 inc
WHERE (
  (inc.closed_at IS NOT NULL AND inc.closed_at >= :since)
  OR
  (inc.closed_at IS NULL AND inc.issue_occurred_at >= :since)
);
