-- ==============================================================
-- Incident drilldown detail, synced into incident_by_status (see
-- app/database/cache.py) — feeds every Incident-column badge (New,
-- In-Progress, Overdue, and their Site-Down variants). Only
-- status IN ('new', 'in_progress') is cached; resolved/closed aren't
-- shown on any badge.
--
-- Site is matched by stripping the 2-letter province prefix off each
-- comma-separated site_text entry against Site.standard_code — a
-- multi-site incident fans out to one row per site (taking only the
-- first site silently dropped the rest from every badge).
--
-- "Other Site" fallback: when a site isn't registered (other_site=true
-- on the source incident), Site Code/Province/District/Commune fall
-- back to the incident's own site_code/province_ref/etc via a CASE on
-- `sites.id IS NULL` — not COALESCE on the field itself, since some
-- registered sites also have a genuinely blank location of their own.
--
-- NMS Code is resolved locally in Python against ne_nms_lookup_cache,
-- not joined here, so the same window function isn't recomputed across
-- every query file that needs it (see ne_nms_lookup.sql).
--
-- Latest INC-WO per (incident, site) is resolved in Python too, not via
-- a per-row LATERAL — that was a correlated subquery against a foreign
-- table (FDW), ~100x slower than one batched query
-- (inc_wo_by_incident_ids.sql) plus a Python pick.
-- ==============================================================

-- name: incident_by_status
SELECT
  inc.incident_id AS "Incident ID",
  inc.id AS "Incident Numeric ID",
  CASE inc.status
    WHEN 'in_progress' THEN 'In Progress'
    ELSE INITCAP(REPLACE(inc.status, '_', ' '))
  END AS "Incident Status",
  ploc.name AS "Site Name",
  sites.id AS "Site Numeric ID",
  COALESCE(sites.standard_code, inc.site_code) AS "Site Code",
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
LEFT JOIN object_160 sites ON site.site_code = sites.standard_code
LEFT JOIN object_162 province
  ON (CASE WHEN sites.id IS NULL THEN inc.province_ref ELSE sites.province END) = province.id
LEFT JOIN object_164 district
  ON (CASE WHEN sites.id IS NULL THEN inc.district ELSE sites.district END) = district.id
LEFT JOIN object_166 commune
  ON (CASE WHEN sites.id IS NULL THEN inc.commune ELSE sites.commune END) = commune.id
LEFT JOIN object_308 ploc ON ploc.id = sites.physical_location
WHERE inc.status IN ('new', 'in_progress')
AND (inc.incident_category IS DISTINCT FROM 'customer_complaint' OR inc.status = 'in_progress')
ORDER BY inc.issue_occurred_at DESC NULLS FIRST;
