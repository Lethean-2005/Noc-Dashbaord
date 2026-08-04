-- ==============================================================
-- Same join/shape as incident_by_status.sql, but scoped down to only
-- VIP/VVIP sites (sites.site_strategic_type) instead of every site
-- company-wide, and to status != 'closed' instead of just
-- ('new', 'in_progress') — so a Resolved incident still shows here.
--
-- NMS Code is resolved locally in Python against ne_nms_lookup_cache, not
-- joined here — see app/database/queries/ne_nms_lookup.sql. The "latest
-- INC-WO per (incident, site)" is resolved the same batched way
-- incident_by_status.sql now uses — see that file's header for why (a
-- per-row LATERAL against the foreign object_324 table was ~100x slower).
--
-- This is a SEPARATE cache from incident_by_status on purpose, same
-- reasoning as incident_site_down already being separate from it:
-- incident_by_status is shared by IncidentService (the Incident card's own
-- New/In-Progress/Overdue badges) and MentorSiteService (its "Site Down"
-- status check), both of which need Resolved EXCLUDED — widening that
-- query directly once already caused a real outage (Incident's drilldown
-- has no pagination; Resolved incidents company-wide pushed it from ~380
-- rows to 3,800+, freezing the page). This table only ever covers VIP/VVIP
-- sites (33 of 4,360 sites, confirmed against real data) — even with every
-- Resolved incident included, the row count stays small, so VipAlarmService
-- can safely keep showing a site's Incident/INC-WO reference through
-- Resolved without repeating that outage.
-- ==============================================================

-- name: vip_incident_status
SELECT
  inc.incident_id AS "Incident ID",
  inc.id AS "Incident Numeric ID",
  CASE inc.status
    WHEN 'in_progress' THEN 'In Progress'
    ELSE INITCAP(REPLACE(inc.status, '_', ' '))
  END AS "Incident Status",
  ploc.fra_site_name AS "Site Name",
  sites.id AS "Site Numeric ID",
  sites.standard_code AS "Site Code",
  inc.issue_occurred_at AS "Occurred At",
  CASE WHEN inc.overdue THEN 'Yes' ELSE 'No' END AS Overdue,
  CASE inc.incident_category
    WHEN 'bss_hardware' THEN 'BSS Hardware'
    WHEN 'bss_software' THEN 'BSS Software'
    WHEN 'oss_platform' THEN 'OSS Platform'
    WHEN 'ip_core' THEN 'IP Core'
    WHEN 'cs_core' THEN 'CS Core'
    WHEN 'ps_core' THEN 'PS Core'
    ELSE INITCAP(REPLACE(inc.incident_category, '_', ' '))
  END AS Category,
  inc.l1_noc_investigation_result AS "L1 NOC Investigation Result",
  sites.hub_site AS "Hub Site",
  INITCAP(sites.site_grade) AS "Site Grade",
  province.name AS "Province",
  district.name AS "District",
  commune.name AS "Commune"
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
) site ON TRUE
JOIN object_160 sites ON site.site_code = sites.standard_code
  AND LOWER(sites.site_strategic_type) IN ('vip', 'vvip')
LEFT JOIN object_162 province ON sites.province = province.id
LEFT JOIN object_164 district ON sites.district = district.id
LEFT JOIN object_166 commune ON sites.commune = commune.id
LEFT JOIN object_308 ploc ON ploc.id = sites.physical_location
WHERE inc.status != 'closed'
ORDER BY inc.issue_occurred_at DESC NULLS FIRST;
