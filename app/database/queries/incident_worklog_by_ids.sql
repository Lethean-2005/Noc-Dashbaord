-- ==============================================================
-- Every Worklog entry (object_362) for a batch of incidents — behind
-- "Site Down by Age"'s own click-through: one site-down incident
-- usually has several worklog updates logged against it over time
-- (NOC/subcon progress notes), newest first, each tagged with who
-- wrote it.
--
-- Scoped to a specific batch of ids (WHERE w.related_record =
-- ANY(:incident_ids)), same "by_ids, safe to join here" pattern as
-- incident_site_down_duration_weekly_by_ids.sql — only ever touches
-- the handful of worklog rows belonging to this id list, not a full
-- table scan.
--
-- related_field is confirmed live to be 4817 for 100% of object_362
-- rows (13,566/13,566 checked) — this table holds nothing but the
-- incident's own Worklog/update-comment field, so no related_field
-- filter is needed.
--
-- Author name is object_3 (user), "name"+"surname" (confirmed live —
-- no full_name/username/email column exists there). LEFT JOIN since a
-- worklog entry with a since-deleted user should still show, just
-- without a name, rather than disappearing.
-- ==============================================================

-- name: incident_worklog_by_ids
SELECT
  inc.id AS "Incident Numeric ID",
  inc.incident_id AS "Incident ID",
  w.data AS "Worklog",
  w.created_at AS "Created At",
  TRIM(CONCAT(u.name, ' ', u.surname)) AS "Created By"
FROM object_362 w
JOIN object_322 inc ON inc.id = w.related_record
LEFT JOIN object_3 u ON u.id = w.created_by
WHERE w.related_record = ANY(:incident_ids)
ORDER BY w.created_at DESC;
