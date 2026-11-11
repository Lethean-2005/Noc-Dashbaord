-- name: incident_resolution_time_weekly
-- Resolution Time — Weekly Trend, sourced from the Incident table
-- (object_322) only, no join. Resolution time = resolved_at -
-- (issue_occurred_at, OR created_at for manually-created incidents —
-- see below). ~80% of incidents have resolved_at filled in a given
-- 30-day window; the rest (still open) are excluded. Grouped into
-- ISO 8601 calendar weeks (2026-W34, 2026-W35, ...) over the last 4
-- weeks (28 days) — the most recent week will be partial (however
-- many days have passed so far), not a full 7-day week, so don't
-- compare it directly against the older, complete weeks.
--
-- Same shape as incident_response_time_weekly.sql — AVG here is a
-- real mean, not a median, same as that query; expect it to run much
-- higher than a "typical" resolution because a small number of very
-- slow resolutions (sometimes many days) drag the mean up hard. Use
-- MIN for a sense of the fast case.
--
-- creation_method ('manually' vs 'automatically', confirmed live —
-- NULL for a small number of older rows, treated the same as
-- 'automatically') decides which start-time to use — same reasoning
-- as incident_response_time_weekly.sql's own header: an automatically-
-- created incident's issue_occurred_at is the alarm's real detection
-- time; a manually-created one's is just whatever the person typing it
-- in chose to enter, sometimes backdated well before the ticket itself
-- existed, so created_at (the system's own real record-creation
-- timestamp) is the honest start time for those instead.
--
-- iso_week is computed off that SAME creation_method-aware timestamp,
-- shifted to Cambodia local time (AT TIME ZONE 'UTC' AT TIME ZONE
-- 'Asia/Phnom_Penh'), not the raw UTC column — see
-- incident_sla_compliance_weekly.sql's header for the full story
-- (confirmed live against Streamline's own "This week" filter: grouping
-- on raw UTC undercounted the current week by 56 incidents, all
-- sitting in the midnight-7am Cambodia boundary window).
SELECT
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
  COUNT(*) AS incident_count,
  MIN(EXTRACT(EPOCH FROM (
    resolved_at - CASE WHEN creation_method = 'manually' THEN created_at ELSE issue_occurred_at END
  )) / 60.0) AS min_minutes,
  AVG(EXTRACT(EPOCH FROM (
    resolved_at - CASE WHEN creation_method = 'manually' THEN created_at ELSE issue_occurred_at END
  )) / 60.0) AS avg_minutes,
  MAX(EXTRACT(EPOCH FROM (
    resolved_at - CASE WHEN creation_method = 'manually' THEN created_at ELSE issue_occurred_at END
  )) / 60.0) AS max_minutes
FROM object_322
WHERE resolved_at IS NOT NULL
  AND (CASE WHEN creation_method = 'manually' THEN created_at ELSE issue_occurred_at END)
      >= ((date_trunc('week', CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Phnom_Penh') - INTERVAL '21 days') AT TIME ZONE 'Asia/Phnom_Penh' AT TIME ZONE 'UTC')
GROUP BY iso_week, category
ORDER BY iso_week;
