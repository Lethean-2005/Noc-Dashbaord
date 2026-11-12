-- ==============================================================
-- "Incident Volume – Week over Week" dashboard card (graph_cards.html),
-- synced into incident_created_trend every INCIDENT_SYNC_INTERVAL_SECONDS.
-- One row per Incident CREATED in the last 30 days — the chart itself
-- only ever displays this-week/last-week (needs at most 14 days), but
-- the cache deliberately keeps a full month of history on hand for
-- later use — regardless of its
-- current status. incident_by_status only ever caches 'new'/'in_progress'
-- incidents (see that query's header comment), so an incident created 6
-- days ago and already closed by now would be silently missing from it —
-- wrong for a "how many incidents came in this week" volume count, which
-- needs every incident regardless of where it stands today.
--
-- Deliberately queries object_322 ALONE, no JOIN — same "conflict with
-- recovery" lesson as incident_closed_trend.sql (see that file's header
-- for the full story: joining two foreign tables directly lost that race
-- on every attempt, 0/18, while a plain filtered SELECT against one
-- foreign table alone succeeds in under a second).
--
-- Bucketing into this-week/last-week x Mon..Sun is done in Python
-- (IncidentService.get_incident_volume_trend()), not here, so the "which
-- week is 'this week'" boundary always reflects the moment the dashboard
-- is viewed rather than whenever this cache last synced.
--
-- :since (bound below, not a literal INTERVAL) is the oldest Monday
-- _available_weeks() can ever offer in this card's own "Compare Weeks"
-- checkboxes — see incident_closed_trend.sql's own comment (and
-- incident_sync_service.py's _oldest_available_monday()) for why a
-- rolling day-count cutoff isn't safe here.
-- ==============================================================

-- :since is Cambodia midnight; compare its UTC equivalent with UTC source timestamps.
-- name: incident_created_trend
SELECT
  inc.incident_id AS "Incident ID",
  inc.id AS "Incident Numeric ID",
  inc.issue_occurred_at AS "Created At"
FROM object_322 inc
WHERE inc.issue_occurred_at >= ((CAST(:since AS timestamp) AT TIME ZONE 'Asia/Phnom_Penh') AT TIME ZONE 'UTC');
