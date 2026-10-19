-- name: sla_policy
-- SLA target/threshold definitions (object_327) — the rules Streamline
-- itself uses to produce object_322's overdue/overdue_response verdicts
-- (see incident_sla_compliance_weekly.sql). Purely a reference table for
-- the SLA Compliance card's "View SLA Policy" popup — NOT joined against
-- object_322 here. category/priority/support_level/site_grade are plain
-- single-value varchar columns on this table (confirmed live), not real
-- arrays, so no array-matching is needed despite Streamline's own
-- "array_string" field-type label for them.
--
-- One rule can key off EITHER priority (L1 NOC / L3 Internal rows) OR
-- site_grade (L2 On-Site rows) — never both — so exactly one of the two
-- is always NULL per row; left as NULL here and handled display-side.
SELECT
  id,
  CASE category
    WHEN 'bss_hardware' THEN 'BSS Hardware'
    WHEN 'bss_software' THEN 'BSS Software'
    WHEN 'oss_platform' THEN 'OSS Platform'
    WHEN 'ip_core' THEN 'IP Core'
    WHEN 'cs_core' THEN 'CS Core'
    WHEN 'ps_core' THEN 'PS Core'
    ELSE INITCAP(REPLACE(category, '_', ' '))
  END AS category,
  INITCAP(priority) AS priority,
  CASE support_level
    WHEN 'l1_noc' THEN 'L1 NOC'
    WHEN 'l2_on_site_support' THEN 'L2 On-Site'
    WHEN 'l3_internal_support' THEN 'L3 Internal'
    ELSE INITCAP(REPLACE(support_level, '_', ' '))
  END AS support_level,
  INITCAP(site_grade) AS site_grade,
  response_time,
  CASE measure_response_time WHEN 'cds' THEN 'CDs' ELSE INITCAP(measure_response_time) END AS measure_response_time,
  resolution_time,
  CASE measure_resolution_time WHEN 'cds' THEN 'CDs' ELSE INITCAP(measure_resolution_time) END AS measure_resolution_time
FROM object_327
WHERE active = true
ORDER BY category, support_level, priority, site_grade;
