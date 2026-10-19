-- name: incident_response_time_weekly
-- Response Time — Weekly Trend, sourced from the Incident table
-- (object_322) only, no join. Response time = take_in_progress_at -
-- issue_occurred_at (when a NOC engineer actually picked up the
-- incident vs when it happened) — the Incident-level equivalent of
-- INC-WO's acknowledged_at, but only ~42% of incidents have
-- take_in_progress_at filled (vs ~99% for the WO field), so this
-- undercounts somewhat. Grouped into ISO 8601 calendar weeks
-- (2026-W34, 2026-W35, ...) over the last 4 weeks (28 days) — the
-- most recent week will be partial (however many days have passed
-- so far), not a full 7-day week, so don't compare it directly
-- against the older, complete weeks.
--
-- iso_week is computed off issue_occurred_at shifted to Cambodia local
-- time (AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Phnom_Penh'), not the raw
-- UTC column — see incident_sla_compliance_weekly.sql's header for the
-- full story (confirmed live against Streamline's own "This week"
-- filter: grouping on raw UTC undercounted the current week by 56
-- incidents, all sitting in the midnight-7am Cambodia boundary window).
SELECT
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
  COUNT(*) AS incident_count,
  MIN(EXTRACT(EPOCH FROM (take_in_progress_at - issue_occurred_at)) / 60.0) AS min_minutes,
  AVG(EXTRACT(EPOCH FROM (take_in_progress_at - issue_occurred_at)) / 60.0) AS avg_minutes,
  MAX(EXTRACT(EPOCH FROM (take_in_progress_at - issue_occurred_at)) / 60.0) AS max_minutes
FROM object_322
WHERE take_in_progress_at IS NOT NULL
  AND issue_occurred_at >= date_trunc('week', CURRENT_DATE) - INTERVAL '21 days'
GROUP BY iso_week, category
ORDER BY iso_week;
