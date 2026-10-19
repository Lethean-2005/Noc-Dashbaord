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
-- Same category CASE mapping and Cambodia-local iso_week as
-- incident_resolution_time_weekly.sql — see that file's header for why
-- (AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Phnom_Penh', not raw UTC).
-- occurred_at/resolved_at stay raw UTC here, same as every other
-- per-incident query — IncidentSyncService converts them via
-- to_local_seconds() at sync time, so shifting them here too would
-- double-convert. The duration itself (resolution_minutes) is a plain
-- subtraction of two UTC timestamps, unaffected by which zone either
-- side displays in. No JOIN needed since category is already a plain
-- column on object_322 itself.
SELECT
  incident_id,
  id AS incident_numeric_id,
  TO_CHAR(issue_occurred_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Phnom_Penh', 'IYYY-"W"IW') AS iso_week,
  CASE incident_category
    WHEN 'bss_hardware' THEN 'BSS Hardware'
    WHEN 'bss_software' THEN 'BSS Software'
    WHEN 'oss_platform' THEN 'OSS Platform'
    WHEN 'ip_core' THEN 'IP Core'
    WHEN 'cs_core' THEN 'CS Core'
    WHEN 'ps_core' THEN 'PS Core'
    ELSE INITCAP(REPLACE(incident_category, '_', ' '))
  END AS category,
  issue_occurred_at AS occurred_at,
  resolved_at,
  EXTRACT(EPOCH FROM (resolved_at - issue_occurred_at)) / 60.0 AS resolution_minutes
FROM object_322
WHERE resolved_at IS NOT NULL
  AND issue_occurred_at >= date_trunc('week', CURRENT_DATE) - INTERVAL '21 days';
