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
-- TWO SEPARATE week-anchors, deliberately NOT one shared GROUP BY —
-- each confirmed live against the user's own manual Streamline filter
-- for its own metric:
--   - Resolution SLA -> closed_at. The ORIGINAL version of this query
--     grouped BOTH metrics by issue_occurred_at's week, giving 1265 for
--     a week where Streamline itself (filtering by Closed At) showed
--     1284. Resolution SLA is fundamentally about incidents CLOSED in
--     a given week — an incident that occurred in week 41 but closed
--     in week 42 belongs in Streamline's week-42 Resolution SLA count,
--     not week 41's.
--   - Response SLA -> created_at, NOT issue_occurred_at. overdue_response
--     is a deadline Streamline itself tracks from the ticket's own
--     creation, not from the (sometimes backdated/estimated)
--     issue_occurred_at — confirmed live the same way: Streamline's own
--     Created At + Overdue (Response) filter matched the created_at-
--     anchored count, not the issue_occurred_at-anchored one.
--
-- response_stats and resolution_stats are combined with a FULL OUTER
-- JOIN (not a plain JOIN) on (iso_week, category, priority) so a
-- bucket that only has response-side or only resolution-side activity
-- in a given week still gets a row instead of silently disappearing.
--
-- Local-time shift (AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Phnom_Penh')
-- applies to EACH anchor the same way issue_occurred_at's own shift
-- always has — created_at and closed_at are stored as naive UTC too
-- (see postgres_sync_utils.py's to_local_seconds()), so grouping on
-- either raw column would put every incident from midnight-7am
-- Cambodia time into the previous day's — and sometimes previous
-- week's — bucket.
WITH response_stats AS (
  SELECT
    TO_CHAR(created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Phnom_Penh', 'IYYY-"W"IW') AS iso_week,
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
    ) AS response_sla_pct
  FROM object_322
  WHERE created_at >= date_trunc('week', CURRENT_DATE) - INTERVAL '21 days'
  GROUP BY 1, 2, 3
),
resolution_stats AS (
  SELECT
    TO_CHAR(closed_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Phnom_Penh', 'IYYY-"W"IW') AS iso_week,
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
    COUNT(*) FILTER (WHERE overdue IS NOT NULL) AS resolution_known_count,
    COUNT(*) FILTER (WHERE overdue = false) AS resolution_met_count,
    ROUND(
      COUNT(*) FILTER (WHERE overdue = false) * 100.0
      / NULLIF(COUNT(*) FILTER (WHERE overdue IS NOT NULL), 0)
    ) AS resolution_sla_pct
  FROM object_322
  WHERE closed_at >= date_trunc('week', CURRENT_DATE) - INTERVAL '21 days'
  GROUP BY 1, 2, 3
)
SELECT
  COALESCE(r.iso_week, s.iso_week) AS iso_week,
  COALESCE(r.category, s.category) AS category,
  COALESCE(r.priority, s.priority) AS priority,
  COALESCE(r.incident_count, 0) AS incident_count,
  COALESCE(r.response_met_count, 0) AS response_met_count,
  r.response_sla_pct AS response_sla_pct,
  COALESCE(s.resolution_known_count, 0) AS resolution_known_count,
  COALESCE(s.resolution_met_count, 0) AS resolution_met_count,
  s.resolution_sla_pct AS resolution_sla_pct
FROM response_stats r
FULL OUTER JOIN resolution_stats s
  ON r.iso_week = s.iso_week AND r.category = s.category AND r.priority = s.priority
ORDER BY 1;
