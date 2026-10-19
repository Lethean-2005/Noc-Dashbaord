-- name: incident_sla_compliance_details
-- Per-incident rows behind the SLA Compliance card's per-week popup
-- (category/priority breakdown — see IncidentService's
-- get_sla_compliance_details() and incident_sla_compliance_weekly.sql's
-- own header for the aggregate sibling this mirrors, same "aggregate
-- query + a plain per-row sibling" split as incident_created_trend.sql).
--
-- Also carries what's needed to match this incident against an
-- sla_policy (object_327) rule for the drilldown's "SLA" column:
--   - support_level: object_322's OWN column — confirmed live against
--     Streamline's own Incident view (INC-0000249969: Support Level
--     "L1 NOC", SLA "High (4 Hours)") that THIS is what Streamline's
--     own per-incident SLA is computed from, not the INC-WO table.
--     A WO can be dispatched to L2 On-Site while the incident's own
--     record stays "L1 NOC" — a WO changes who's working it, not the
--     incident's own SLA classification. (An earlier version of this
--     query pulled support_level from the latest WO instead — wrong,
--     it showed "Gold (6 Hours)" for that same incident when Streamline
--     itself says "High (4 Hours)".) In practice this column is
--     'l1_noc' for effectively every incident (confirmed: 248,166 of
--     248,168), so the L2 On-Site/L3 Internal sla_policy rules will
--     rarely if ever match here — that's correct, not a bug.
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
  inc.overdue
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
WHERE inc.issue_occurred_at >= date_trunc('week', CURRENT_DATE) - INTERVAL '21 days';
