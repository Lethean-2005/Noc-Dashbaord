-- ==============================================================
-- Enrichment step for the "Incident Volume – Week over Week" dashboard
-- card's drilldown table (see incident_created_trend.sql for the base
-- list of recently-created Incidents). Resolves status, category,
-- severity, site, vendor, and location for a specific batch of
-- Incident numeric ids — same content/shape as
-- incident_closed_trend_by_ids.sql (kept as its own file rather than
-- shared, matching this codebase's existing pattern of separate
-- near-identical query files per feature, e.g. inc_wo_by_status.sql /
-- inc_wo_site_down.sql / inc_wo_category_power.sql).
--
-- Scoped to a specific batch of ids (WHERE inc.id = ANY(:incident_ids)),
-- same pattern as inc_wo_by_incident_ids.sql — safe to join here (unlike
-- incident_created_trend.sql's own base query, which stays a plain
-- single-table SELECT) since the join only ever touches the handful of
-- rows matching this id list, not a full-table scan.
--
-- "Actual Ran Vendor" is the site's raw numeric code (sites.actual_ran_vendor)
-- — resolved to a real vendor name in Python via
-- app.utils.nms.ACTUAL_RAN_VENDOR_TO_NMS_CODE/NMS_NAMES (same lookup
-- map_view_service.py already uses), not here — only 3 of the codes
-- this column actually holds are confirmed-correct against Streamline's
-- own data (see that module's own header), so resolving it in one
-- shared place keeps that caveat from being silently duplicated/
-- forgotten in a second CASE expression.
-- ==============================================================

-- name: incident_created_trend_by_ids
SELECT
  inc.id AS "Incident Numeric ID",
  inc.incident_id AS "Incident ID",
  CASE inc.status
    WHEN 'in_progress' THEN 'In Progress'
    ELSE INITCAP(REPLACE(inc.status, '_', ' '))
  END AS "Incident Status",
  CASE inc.incident_category
    WHEN 'bss_hardware' THEN 'BSS Hardware'
    WHEN 'bss_software' THEN 'BSS Software'
    WHEN 'oss_platform' THEN 'OSS Platform'
    WHEN 'ip_core' THEN 'IP Core'
    WHEN 'cs_core' THEN 'CS Core'
    WHEN 'ps_core' THEN 'PS Core'
    ELSE INITCAP(REPLACE(inc.incident_category, '_', ' '))
  END AS "Category",
  INITCAP(inc.severity) AS "Severity",
  ploc.name AS "Site Name",
  COALESCE(sites.standard_code, inc.site_code) AS "Site Code",
  sites.actual_ran_vendor AS "Actual Ran Vendor",
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
WHERE inc.id = ANY(:incident_ids);
