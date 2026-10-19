-- ==============================================================
-- Per-incident Site Down detail for the last 30 days, cached as
-- incident_site_down_root_cause for incident_sync_service.py.
--
-- "Root Cause Category" is the real category Streamline assigns to
-- the incident on resolution — a Reference-to-list field, which the
-- platform stores as a row in the generic mapping table object_10
-- rather than as a column on object_322 itself. object_10 holds every
-- Reference-to-list field on every object, keyed by that field's own
-- id in source_field; 4758 is this field's id for Incidents (object_322).
-- "None" is a legitimate result, not a join miss: either the incident
-- is still open (RCA Category is only set when it's resolved) or it
-- auto-closed when its alarm cleared, which never sets one.
--
-- Deliberately NOT filtered to incident_category = 'site_down' here —
-- adding that one WHERE clause makes this exact query fail "conflict
-- with recovery" on every single attempt, 6/6, confirmed live twice.
-- The unfiltered version (this one) succeeds every time it's been run.
-- Whatever makes that filter change the query plan enough to matter
-- isn't understood yet, so incident_sync_service.py's
-- sync_site_down_root_cause() fetches every incident and filters to
-- Site Down in Python instead — same "avoid it rather than chase why"
-- call as dropping the ROW_NUMBER()/"Times" ranking below.
--
-- object_10 is a platform-wide table (every Reference-to-list field on
-- every object, not just this one), so it carries the same "conflict
-- with recovery" replica-timing exposure as object_138 — see
-- ape_alarm.sql's own header for that risk.
--
-- A small number of incidents (confirmed live) have more than one Root
-- Cause Category selected at once — this returns one row per
-- (incident, category) rather than picking just one, so incident_id is
-- deliberately NOT unique in incident_site_down_root_cause. See this
-- table's own schema note in app/database/cache.py.
--
-- "Times" (how many times a site has gone down in this window) is
-- computed in Python too, not via SQL's ROW_NUMBER() — that window
-- function forces Postgres to fully sort/materialize the whole result
-- before returning anything, same "conflict with recovery" exposure.
-- No ORDER BY here either, for the same reason — nothing needs
-- Postgres to sort before streaming rows back; final ordering for
-- display comes from the cache repository's own order_by when reading
-- out of SQLite.
--
-- :since (bound below, not a literal INTERVAL) is the oldest Monday
-- _available_weeks() can ever offer in "Compare Weeks" checkboxes
-- dashboard-wide — see incident_closed_trend.sql's own comment (and
-- incident_sync_service.py's _oldest_available_monday()) for why a
-- rolling day-count cutoff isn't safe here. Bound as a date (not a
-- timestamp) the same way CURRENT_DATE was before, comparing fine
-- against issue_occurred_at's own timestamp column either way.
-- ==============================================================

-- name: incident_site_down_root_cause
SELECT
  inc.incident_id AS "Incident ID",
  inc.site_text AS "Site",
  inc.incident_category AS "Incident Category",
  inc.actual_root_cause AS "Actual Root Cause",
  COALESCE(cat.root_cause_category_name, 'None') AS "Root Cause Category",
  inc.issue_occurred_at AS "Occurred At"
FROM object_322 inc
LEFT JOIN object_10 rca_link
  ON rca_link.source_field = 4758
  AND rca_link.source_record_id = inc.id
LEFT JOIN object_356 cat
  ON cat.id = rca_link.target_record_id
WHERE inc.issue_occurred_at >= :since;
