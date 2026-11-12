-- ==============================================================
-- "Site-Down Duration — Weekly Trend" card (Performance page).
-- Step 1 of 2 (see incident_site_down_duration_weekly_by_ids.sql for
-- step 2, which resolves Site Name/Code — one incident can fan out to
-- several site rows there). One row per Site Down incident closed in
-- the last 30 days, with both issue_occurred_at and resolved_at so
-- duration (resolved_at - issue_occurred_at) can be bucketed into
-- <4h / 4-8h / 8-12h / 12-24h / >24h.
--
-- Deliberately no JOIN here — confirmed live that adding the
-- LATERAL-UNNEST + object_160/308 join directly to this step's ~5,500-
-- row/30-day scan hits "conflict with recovery" every time (same
-- replication-race lesson incident_closed_trend.sql's header
-- describes for object_324); splitting into this cheap unjoined query
-- plus a second query scoped to just this batch's ids (a few hundred
-- per sync cycle, not thousands) is what actually avoids the race.
--
-- Filtered on resolved_at IS NOT NULL, not just status = 'closed' —
-- resolved_at is what the duration is actually computed from, and a
-- small number of 'closed' incidents have no resolved_at set (closed
-- a different way — see incident_sla_compliance_weekly.sql's header
-- for the same caveat on a different field).
--
-- :since (bound below, not a literal INTERVAL) is the oldest Monday
-- _available_weeks() can ever offer in the "Filter by Week"/"Compare
-- Weeks" checkboxes dashboard-wide — see incident_sync_service.py's
-- own sync_site_down_duration_weekly() for how it's computed. A plain
-- rolling "NOW() - INTERVAL '30 days'" instead lands on whatever day
-- of the week the sync happens to run, not a Monday — depending on
-- today's weekday that's sometimes a few days SHORTER than the oldest
-- full ISO week the filter checkboxes could select, so "check every
-- available week" silently excluded a slice of real data that "No
-- filter" included (same bug class already confirmed live on this
-- card's own week-count mismatch: 458 vs 434 with the checkbox list
-- itself too short — see _WEEKS_AVAILABLE's own docstring). Anchoring
-- to the same Monday the filter UI itself computes from closes this
-- other half of that gap: every synced row is now guaranteed to fall
-- inside one of the offered weeks, regardless of which weekday the
-- sync cycle happens to run on.
-- ==============================================================

-- :since is Cambodia midnight; compare its UTC equivalent with UTC source timestamps.
-- name: incident_site_down_duration_weekly
SELECT
  inc.incident_id AS "Incident ID",
  inc.id AS "Incident Numeric ID",
  inc.issue_occurred_at AS "Occurred At",
  inc.resolved_at AS "Resolved At",
  inc.closed_at AS "Closed At"
FROM object_322 inc
WHERE inc.incident_category = 'site_down'
  AND inc.status = 'closed'
  AND inc.resolved_at IS NOT NULL
  AND inc.closed_at >= ((CAST(:since AS timestamp) AT TIME ZONE 'Asia/Phnom_Penh') AT TIME ZONE 'UTC');
