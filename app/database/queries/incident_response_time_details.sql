-- name: incident_response_time_details
-- Per-incident rows behind "Response Time — Weekly Trend"'s duration
-- breakdown (bucketed by response_minutes into ≤1m/1m-15m/15m-1h/1h-4h/
-- 4h-24h/>24h — see IncidentService._RESPONSE_DURATION_BUCKET_LABELS).
-- incident_response_time_weekly.sql already computes MIN/AVG/MAX per
-- (week, category) in SQL, but that collapses away which incident
-- actually IS the min/max — this is the same filter/window with the
-- GROUP BY removed, one row per incident, so the bucket counts can be
-- computed in Python and clicking one can show the real incidents
-- behind it (same "aggregate query + a plain per-row sibling" split as
-- incident_created_trend.sql / incident_created_trend_by_ids.sql).
--
-- Same category CASE mapping, same creation_method-aware start time,
-- and same Cambodia-local iso_week as incident_response_time_weekly.sql
-- — see that file's header for the full "why" (an automatically-
-- created incident's issue_occurred_at is the alarm's real detection
-- time; a manually-created one's is just whatever the person typing it
-- in chose to enter, sometimes backdated, so created_at is the honest
-- start time for those instead — confirmed live this isn't academic,
-- it moved Week 42's real MAX response time from 1583 to 746 minutes).
--
-- occurred_at (now creation_method-aware, not always issue_occurred_at)
-- /took_in_progress_at stay raw UTC here, same as every other
-- per-incident query (incident_created_trend.sql etc.) —
-- IncidentSyncService converts them via to_local_seconds() at sync
-- time, so shifting them here too would double-convert. The duration
-- itself (response_minutes) is a plain subtraction of two UTC
-- timestamps, unaffected by which zone either side displays in.
-- No JOIN needed (unlike incident_created_trend's site/province columns)
-- since category is already a plain column on object_322 itself.
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
  take_in_progress_at AS took_in_progress_at,
  EXTRACT(EPOCH FROM (
    take_in_progress_at - CASE WHEN creation_method = 'manually' THEN created_at ELSE issue_occurred_at END
  )) / 60.0 AS response_minutes,
  INITCAP(COALESCE(creation_method, 'automatically')) AS creation_method
FROM object_322
WHERE take_in_progress_at IS NOT NULL
  AND (CASE WHEN creation_method = 'manually' THEN created_at ELSE issue_occurred_at END)
      >= date_trunc('week', CURRENT_DATE) - INTERVAL '21 days';
