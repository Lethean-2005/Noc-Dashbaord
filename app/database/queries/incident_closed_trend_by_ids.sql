-- ==============================================================
-- Step 2 of 2 for the "Incidents Closed – Week over Week" dashboard card
-- (see incident_closed_trend.sql for step 1, which already guarantees
-- every id here is status='closed' OR 'resolved'). Resolves each
-- numeric id to its text incident_id (the cache table's primary key)
-- plus enough drilldown detail (site, category, location) to make the
-- "Incidents Closed" drilldown table actually useful — not just a bare
-- incident_id/closed_at list.
--
-- Scoped to a specific batch of ids (WHERE inc.id = ANY(:incident_ids)),
-- same pattern as inc_wo_by_incident_ids.sql — safe to join here (unlike
-- incident_closed_trend.sql's step 1) since the join only ever touches
-- the handful of rows matching this id list, not a full-table scan.
--
-- Site resolution mirrors incident_by_status.sql exactly (see that
-- file's header comment for the site_text-parsing/"Other Site" fallback
-- reasoning) — kept in sync with it by hand since duplicating a LATERAL
-- across query files is simpler than sharing SQL fragments here.
-- ==============================================================

-- name: incident_closed_trend_by_ids
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
  ploc.name AS "Site Name",
  COALESCE(sites.standard_code, inc.site_code) AS "Site Code",
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
