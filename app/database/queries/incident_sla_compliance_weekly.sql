-- name: incident_sla_compliance_weekly
-- SLA Compliance — Weekly Trends, sourced from the Incident table
-- (object_322) only, no join. Two separate SLA verdicts, both
-- Streamline's own real pass/fail judgment (not calculated here):
--   - Response SLA:   overdue_response (bool) — always filled in, so
--                      every incident in the window counts.
--   - Resolution SLA: overdue (bool) — sometimes left blank by
--                      Streamline (no verdict given, e.g. incidents
--                      closed through a different workflow). Blanks
--                      are excluded from resolution_sla_pct rather
--                      than guessed at from due_date ourselves —
--                      confirmed live that computing it from due_date
--                      directly would count ~2,850 blank incidents as
--                      "on time" that Streamline itself never graded,
--                      inflating the number above what Streamline
--                      would actually report. Deliberately NOT
--                      restricted to one status (e.g. status =
--                      'resolved' only) — an incident can reach either
--                      'resolved' or 'closed' as its terminal state
--                      (see incident_closed_trend.sql's own header for
--                      why those two aren't interchangeable — many
--                      incidents, especially Customer Complaint, sit
--                      at 'resolved' and never formally reach
--                      'closed'), and "overdue IS NOT NULL" already
--                      picks up a real verdict from whichever one
--                      applies, without needing to know which.
-- overdue/overdue_response: True = missed the deadline (failed),
-- False = met the deadline (passed).
--
-- iso_week is computed off issue_occurred_at shifted to Cambodia local
-- time (AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Phnom_Penh'), not the raw
-- UTC column — issue_occurred_at is stored as naive UTC (same as every
-- other timestamp on this table, see postgres_sync_utils.py's
-- to_local_seconds()), so grouping on the raw value put every incident
-- from midnight-7am Cambodia time (5pm-midnight UTC the day before)
-- into the PREVIOUS week's bucket. Confirmed live against Streamline's
-- own "This week" filter (Overdue Response = false): the raw-UTC
-- grouping undercounted by 56 incidents, all sitting in exactly that
-- boundary window — this local-time version matches Streamline's count.
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
  INITCAP(COALESCE(priority, 'Unknown')) AS priority,
  COUNT(*) AS incident_count,
  COUNT(*) FILTER (WHERE overdue_response = false) AS response_met_count,
  ROUND(
    COUNT(*) FILTER (WHERE overdue_response = false) * 100.0 / COUNT(*)
  ) AS response_sla_pct,
  COUNT(*) FILTER (WHERE overdue IS NOT NULL) AS resolution_known_count,
  COUNT(*) FILTER (WHERE overdue = false) AS resolution_met_count,
  ROUND(
    COUNT(*) FILTER (WHERE overdue = false) * 100.0
    / NULLIF(COUNT(*) FILTER (WHERE overdue IS NOT NULL), 0)
  ) AS resolution_sla_pct
FROM object_322
WHERE issue_occurred_at >= date_trunc('week', CURRENT_DATE) - INTERVAL '21 days'
GROUP BY iso_week, category, priority
ORDER BY iso_week;
