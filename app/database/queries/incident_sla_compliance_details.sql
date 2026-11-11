-- name: incident_sla_compliance_details
-- Per-incident rows behind the SLA Compliance card's per-week popup
-- (category/priority breakdown — see IncidentService's
-- get_sla_compliance_details() and incident_sla_compliance_weekly.sql's
-- own header for the aggregate sibling this mirrors, same "aggregate
-- query + a plain per-row sibling" split as incident_created_trend.sql).
--
-- THREE separate week columns, not one — confirmed live this matters:
-- iso_week (issue_occurred_at-anchored) is what "Not Graded"/"total"
-- drilldown links filter on; response_iso_week (created_at-anchored)
-- and resolution_iso_week (closed_at-anchored) exist specifically so
-- "Response Met"/"Resolution Met"/"Resolution Graded" drilldown links
-- can filter on the SAME anchor incident_sla_compliance_weekly.sql used
-- to compute that cell's own count. Before these existed, EVERY
-- drilldown link filtered on iso_week regardless of metric — harmless
-- for Response Met in practice (created_at and issue_occurred_at are
-- almost always the same week), but a real, confirmed bug for
-- Resolution Met/Graded: one real week's "Resolution Met: 21/43"
-- popup cell linked to only 17 incidents instead of 43, because
-- resolution_known_count is closed_at-anchored while the drilldown was
-- filtering by issue_occurred_at — resolution can take far longer than
-- response, so closed_at drifts away from issue_occurred_at's week much
-- more than created_at does. resolution_iso_week is NULL for an
-- incident still open (no closed_at yet) — correct, since an open
-- incident can't belong to any "closed in week X" bucket yet.
--
-- Also carries what's needed to match this incident against an
-- sla_policy (object_327) rule for the drilldown's "SLA" column:
--   - support_level: use the incident's own value, not the latest WO.
--     WO assignment does not change the incident's SLA classification.
--   - site_grade: NOT on object_322 itself — joined from the Sites
--     table (object_160) via the same site_text-stripping LATERAL as
--     incident_by_status.sql (see that query's own header for why),
--     kept for the rare case support_level really is L2 On-Site. A
--     multi-site incident fans out to more than one row here too —
--     deduped back to one row per incident in Python
--     (sync_sla_compliance_details(), same "keep first row seen"
--     pattern as sync_incident_closed_trend()).
SELECT
  inc.incident_id,
  inc.id AS incident_numeric_id,
  TO_CHAR(inc.issue_occurred_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Phnom_Penh', 'IYYY-"W"IW') AS iso_week,
  TO_CHAR(inc.created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Phnom_Penh', 'IYYY-"W"IW') AS response_iso_week,
  CASE WHEN inc.closed_at IS NOT NULL THEN
    TO_CHAR(inc.closed_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Phnom_Penh', 'IYYY-"W"IW')
  END AS resolution_iso_week,
  CASE inc.incident_category
    WHEN 'bss_hardware' THEN 'BSS Hardware'
    WHEN 'bss_software' THEN 'BSS Software'
    WHEN 'oss_platform' THEN 'OSS Platform'
    WHEN 'ip_core' THEN 'IP Core'
    WHEN 'cs_core' THEN 'CS Core'
    WHEN 'ps_core' THEN 'PS Core'
    ELSE INITCAP(REPLACE(inc.incident_category, '_', ' '))
  END AS category,
  INITCAP(COALESCE(inc.priority, 'Unknown')) AS priority,
  CASE inc.support_level
    WHEN 'l1_noc' THEN 'L1 NOC'
    WHEN 'l2_on_site_support' THEN 'L2 On-Site'
    WHEN 'l3_internal_support' THEN 'L3 Internal'
    ELSE INITCAP(REPLACE(inc.support_level, '_', ' '))
  END AS support_level,
  NULLIF(INITCAP(site.site_grade), '') AS site_grade,
  inc.issue_occurred_at AS occurred_at,
  inc.overdue_response,
  inc.overdue,
  COALESCE(cat.root_cause_category_name, 'Not Assigned') AS root_cause_category
FROM object_322 inc
LEFT JOIN LATERAL (
  SELECT DISTINCT
    TRIM(
      REGEXP_REPLACE(
        NULLIF(TRIM(site_part), ''),
        '^[A-Za-z]{2}',
        ''
      )
    ) AS site_code
  FROM UNNEST(STRING_TO_ARRAY(inc.site_text, ',')) AS site_part
) site_part_lookup ON TRUE
LEFT JOIN object_160 site ON site_part_lookup.site_code = site.standard_code
-- Root Cause Category — same object_10/object_356 reference-to-list join
-- incident_site_down_root_cause.sql already uses (see that query's own
-- header for why it's a join and not a plain column: Streamline stores
-- it as a Reference-to-list field, keyed by field id 4758). "Not
-- Assigned" is a real result, not a join miss — only set once an
-- incident is resolved.
-- A small number of incidents have more than one category selected at
-- once (confirmed live) — same multi-row fan-out the site_text LATERAL
-- above already produces for multi-site incidents, absorbed by the same
-- "keep first row seen" dedup (sync_sla_compliance_details()).
LEFT JOIN object_10 rca_link
  ON rca_link.source_field = 4758
  AND rca_link.source_record_id = inc.id
LEFT JOIN object_356 cat ON cat.id = rca_link.target_record_id
-- OR across all three anchors (not just issue_occurred_at) — an
-- incident that occurred over 3 weeks ago but closed this week needs to
-- still appear here, or the Resolution Met/Graded drilldown would miss
-- it even with resolution_iso_week above, since it'd never make it into
-- this table at all. Mirrors incident_sla_compliance_weekly.sql's own
-- 3 separate CTEs, each filtering on its own anchor.
WHERE inc.issue_occurred_at >= ((date_trunc('week', CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Phnom_Penh') - INTERVAL '21 days') AT TIME ZONE 'Asia/Phnom_Penh' AT TIME ZONE 'UTC')
   OR inc.created_at >= ((date_trunc('week', CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Phnom_Penh') - INTERVAL '21 days') AT TIME ZONE 'Asia/Phnom_Penh' AT TIME ZONE 'UTC')
   OR inc.closed_at >= ((date_trunc('week', CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Phnom_Penh') - INTERVAL '21 days') AT TIME ZONE 'Asia/Phnom_Penh' AT TIME ZONE 'UTC');
