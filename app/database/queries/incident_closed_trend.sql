-- ==============================================================
-- "Incidents Closed – Week over Week" dashboard card (graph_cards.html),
-- synced into incident_closed_trend every INCIDENT_SYNC_INTERVAL_SECONDS.
--
-- Step 1 of 2 (see incident_closed_trend_by_ids.sql for step 2). One row
-- per Incident that reached 'closed' OR 'resolved' in the last 30 days
-- — the chart itself only ever displays this-week/last-week (needs at
-- most 14 days), but the cache deliberately keeps a full month of
-- history on hand for later use — reads object_322's OWN closed_at/
-- resolved_at directly, not the work order's resolved_at (object_324).
--
-- An earlier version drove this off object_324 (work order) resolved_at
-- instead, on the assumption that closing always happens through a WO.
-- Confirmed live that assumption was wrong: for one sample day, 118
-- Incidents created that day were already status='closed', but only 51
-- of them had a work order resolved that same day at all — the other 67
-- were closed with NO work order ever created for them (wo_status: NULL,
-- confirmed directly against Postgres), so they were silently invisible
-- to the old WO-driven query, not delayed to a different day. That fix
-- moved this to object_322's own closed_at column, set regardless of
-- whether a WO exists.
--
-- That alone was still incomplete, confirmed live a second time: for
-- Customer Complaint specifically, 8,719 Incidents sit at
-- status='resolved' with closed_at NEVER set at all (has_closed_at=0
-- across every one of them) — 'resolved' is this category's real
-- terminal state far more often than 'closed' (in one 30-day sample,
-- 4,298 reached 'resolved' vs only 421 that reached 'closed'), so a
-- closed_at-only query was blind to the large majority of what
-- actually completed. COALESCE(closed_at, resolved_at) picks up
-- whichever terminal timestamp an Incident actually has — closed_at
-- for one that reached 'closed' (object_322.resolved_at is populated
-- for ~99% of these too, but closed_at takes priority since that's the
-- later, more final timestamp), resolved_at for one that stopped at
-- 'resolved' and never formally closed. Confirmed live neither status
-- ever has BOTH fields null, so this never silently drops a row.
--
-- Still deliberately queries object_322 ALONE, no JOIN to object_324 —
-- same "conflict with recovery" lesson noted before: joining two foreign
-- tables directly lost that race on every attempt (confirmed live: 0/18
-- across 3 test rounds), while a plain filtered SELECT against one
-- foreign table alone succeeds in under a second.
--
-- Bucketing into this-week/last-week x Mon..Sun is done in Python
-- (IncidentService.get_incident_closed_trend()), not here, so the "which
-- week is 'this week'" boundary always reflects the moment the dashboard
-- is viewed rather than whenever this cache last synced.
--
-- Customer Complaint gets its own status rule, by request: only
-- status='resolved' counts as "closed" for this category — a Customer
-- Complaint that later reaches 'closed' is deliberately excluded here
-- (unlike every other category, where 'closed' still counts). Every
-- other category is unaffected, keeping status IN ('closed', 'resolved')
-- and the COALESCE(closed_at, resolved_at) timestamp fallback above.
--
-- :since (bound below, not a literal INTERVAL) is the oldest Monday
-- _available_weeks() can ever offer in this card's own "Compare Weeks"
-- checkboxes (incident_sync_service.py's _oldest_available_monday()) —
-- a plain rolling "NOW() - INTERVAL '30 days'" lands on whatever
-- weekday the sync happens to run, not a Monday, so it could cover
-- LESS than the oldest full ISO week the checkboxes offer depending on
-- today's weekday (same bug class confirmed live on
-- incident_site_down_duration_weekly: 458 vs 434 with every available
-- week checked). Anchoring to the same Monday the filter UI computes
-- from guarantees every synced row falls inside one of the offered
-- weeks, regardless of which weekday sync runs on.
-- ==============================================================

-- name: incident_closed_trend
SELECT
  inc.incident_id AS "Incident ID",
  inc.id AS "Incident Numeric ID",
  COALESCE(inc.closed_at, inc.resolved_at) AS "Closed At"
FROM object_322 inc
WHERE (
    (inc.incident_category = 'customer_complaint' AND inc.status = 'resolved')
    OR (inc.incident_category IS DISTINCT FROM 'customer_complaint' AND inc.status IN ('closed', 'resolved'))
  )
  AND COALESCE(inc.closed_at, inc.resolved_at) >= :since;
