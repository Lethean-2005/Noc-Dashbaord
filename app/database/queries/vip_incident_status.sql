-- ==============================================================
-- Same join/shape as incident_by_status.sql, scoped to VIP/VVIP sites
-- and status != 'closed' (so Resolved still shows here). NMS Code is
-- resolved locally against ne_nms_lookup_cache, same as that file.
--
-- Kept as its own cache rather than merged into incident_by_status —
-- that one excludes Resolved on purpose (widening it once caused a real
-- outage: Incident's drilldown has no pagination, and Resolved company-
-- wide pushed it to 3,800+ rows). Scoped to just VIP/VVIP sites, this
-- stays small even with Resolved included, so it's safe here.
--
-- "VIP/VVIP site" is Postgres's own site_strategic_type OR a site in
-- :mssql_vip_site_codes (MSSQL's TBL_SITE.SITE_STRATEGIC, passed in by
-- IncidentSyncService.sync_vip_incident_status() from vip_site_cache) —
-- the two systems' site data can disagree (confirmed live for site
-- 1517/CHI_PECH on 2026-09-22: MSSQL says VIP, Postgres says
-- none_strategic), and per the user, MSSQL's site data specifically is
-- kept more current than Postgres's own. OR, not AND: this only ever
-- widens which sites' incidents show up, never narrows the existing
-- Postgres-flagged set. An empty :mssql_vip_site_codes list is safe —
-- = ANY() over an empty array matches nothing, verified directly
-- against Postgres — so this never needs special-casing "no MSSQL
-- codes yet".
-- ==============================================================

-- name: vip_incident_status
SELECT
  inc.incident_id AS "Incident ID",
  inc.id AS "Incident Numeric ID",
  CASE inc.status
    WHEN 'in_progress' THEN 'In Progress'
    ELSE INITCAP(REPLACE(inc.status, '_', ' '))
  END AS "Incident Status",
  ploc.name AS "Site Name",
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
  AND (
    LOWER(sites.site_strategic_type) IN ('vip', 'vvip')
    OR sites.standard_code = ANY(:mssql_vip_site_codes)
  )
LEFT JOIN object_162 province ON sites.province = province.id
LEFT JOIN object_164 district ON sites.district = district.id
LEFT JOIN object_166 commune ON sites.commune = commune.id
LEFT JOIN object_308 ploc ON ploc.id = sites.physical_location
WHERE inc.status != 'closed'
ORDER BY inc.issue_occurred_at DESC NULLS FIRST;
