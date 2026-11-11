-- name: incident_response_time_weekly
-- Response Time — Weekly Trend, sourced from the Incident table
-- (object_322) only, no join. Response time = take_in_progress_at -
-- (issue_occurred_at, OR created_at for manually-created incidents —
-- see below) — the Incident-level equivalent of INC-WO's
-- acknowledged_at, but only ~42% of incidents have take_in_progress_at
-- filled (vs ~99% for the WO field), so this undercounts somewhat.
-- Grouped into ISO 8601 calendar weeks (2026-W34, 2026-W35, ...) over
-- the last 4 weeks (28 days) — the most recent week will be partial
-- (however many days have passed so far), not a full 7-day week, so
-- don't compare it directly against the older, complete weeks.
--
-- creation_method ('manually' vs 'automatically', confirmed live —
-- NULL for a small number of older rows, treated the same as
-- 'automatically') decides which start-time to use: an automatically-
-- created incident's issue_occurred_at is the alarm's own real
-- detection time, trustworthy as-is. A MANUALLY-created one's
-- issue_occurred_at is just whatever the person typing it in chose to
-- enter — sometimes backdated well before the ticket itself actually
-- existed — so created_at (the system's own real record-creation
-- timestamp) is the honest "when did this incident's clock start" for
-- those. Confirmed live the difference is real, not academic: for
-- Week 42, MAX response time dropped from 1583 minutes (26.4h, using
-- issue_occurred_at always) to 746 minutes (12.4h, using this
-- creation_method split) — a few backdated manual tickets were
-- inflating the real worst-case response time by more than 2x.
--
-- iso_week is computed off that SAME creation_method-aware timestamp,
-- shifted to Cambodia local time (AT TIME ZONE 'UTC' AT TIME ZONE
-- 'Asia/Phnom_Penh'), not the raw UTC column — see
-- incident_sla_compliance_weekly.sql's header for the full story on
-- why the local-time shift itself matters (confirmed live against
-- Streamline's own "This week" filter: grouping on raw UTC undercounted
-- the current week by 56 incidents, all sitting in the midnight-7am
-- Cambodia boundary window).
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
    take_in_progress_at - CASE WHEN creation_method = 'manually' THEN created_at ELSE issue_occurred_at END
  )) / 60.0) AS min_minutes,
  AVG(EXTRACT(EPOCH FROM (
    take_in_progress_at - CASE WHEN creation_method = 'manually' THEN created_at ELSE issue_occurred_at END
  )) / 60.0) AS avg_minutes,
  MAX(EXTRACT(EPOCH FROM (
    take_in_progress_at - CASE WHEN creation_method = 'manually' THEN created_at ELSE issue_occurred_at END
  )) / 60.0) AS max_minutes
FROM object_322
WHERE take_in_progress_at IS NOT NULL
  AND (CASE WHEN creation_method = 'manually' THEN created_at ELSE issue_occurred_at END)
      >= ((date_trunc('week', CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Phnom_Penh') - INTERVAL '21 days') AT TIME ZONE 'Asia/Phnom_Penh' AT TIME ZONE 'UTC')
GROUP BY iso_week, category
ORDER BY iso_week;
