-- name: incident_resolution_time_details
-- Per-incident rows behind "Resolution Time — Weekly Trend"'s duration
-- breakdown (bucketed by resolution_minutes — see
-- IncidentService._RESOLUTION_DURATION_BUCKET_LABELS in dashboard.py).
-- incident_resolution_time_weekly.sql already computes MIN/AVG/MAX per
-- (week, category) in SQL, but that collapses away which incident
-- actually IS the min/max — this is the same filter/window with the
-- GROUP BY removed, one row per incident, so the bucket counts can be
-- computed in Python and clicking one can show the real incidents
-- behind it (same "aggregate query + a plain per-row sibling" split as
-- incident_response_time_details.sql).
--
-- Same category CASE mapping, same creation_method-aware start time,
-- and same Cambodia-local iso_week as incident_resolution_time_weekly.sql
-- — see that file's header for the full "why" (an automatically-
-- created incident's issue_occurred_at is the alarm's real detection
-- time; a manually-created one's is just whatever the person typing it
-- in chose to enter, sometimes backdated, so created_at is the honest
-- start time for those instead).
--
-- occurred_at (now creation_method-aware, not always issue_occurred_at)
-- /resolved_at stay raw UTC here, same as every other per-incident
-- query — IncidentSyncService converts them via to_local_seconds() at
-- sync time, so shifting them here too would double-convert. The
-- duration itself (resolution_minutes) is a plain subtraction of two
-- UTC timestamps, unaffected by which zone either side displays in.
-- No JOIN needed since category is already a plain column on
-- object_322 itself.
SELECT
  incident_id,
  id AS incident_numeric_id,
  TO_CHAR(
    (CASE WHEN creation_method = 'manually' THEN created_at ELSE issue_occurred_at END)
    AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Phnom_Penh', 'IYYY-"W"IW'
  ) AS iso_week,
  CASE incident_category
    WHEN 'bss_hardware' THEN 'BSS Hardware'
    WHEN 'bss_software' THEN 'BSS Software'
    WHEN 'oss_platform' THEN 'OSS Platform'
    WHEN 'ip_core' THEN 'IP Core'
    WHEN 'cs_core' THEN 'CS Core'
    WHEN 'ps_core' THEN 'PS Core'
    ELSE INITCAP(REPLACE(incident_category, '_', ' '))
  END AS category,
  CASE WHEN creation_method = 'manually' THEN created_at ELSE issue_occurred_at END AS occurred_at,
  resolved_at,
  EXTRACT(EPOCH FROM (
    resolved_at - CASE WHEN creation_method = 'manually' THEN created_at ELSE issue_occurred_at END
  )) / 60.0 AS resolution_minutes,
  INITCAP(COALESCE(creation_method, 'automatically')) AS creation_method
FROM object_322
WHERE resolved_at IS NOT NULL
  AND (CASE WHEN creation_method = 'manually' THEN created_at ELSE issue_occurred_at END)
      >= ((date_trunc('week', CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Phnom_Penh') - INTERVAL '21 days') AT TIME ZONE 'Asia/Phnom_Penh' AT TIME ZONE 'UTC');
