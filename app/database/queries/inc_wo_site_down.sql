-- ==============================================================
-- INC-WO Site Down — for the "INC-WO Site Down" card on the Custom
-- Dashboard (reports/index.html), synced into the local
-- "inc_wo_site_down" cache table (see app/database/cache.py) every
-- INCIDENT_SYNC_INTERVAL_SECONDS.
--
-- Same join shape as inc_wo_by_status.sql, but narrowed to only
-- category = 'site_down' work orders that aren't yet resolved/closed —
-- this card's 5 badges (Hub-Site, Diamond, Gold, Silver, Bronze) are a
-- site-grade/hub breakdown of that set, computed in
-- app/services/incwo/incwo_service.py from this cache. Same "Other Site"
-- fallback as inc_wo_by_status.sql too — see that file's header.
-- ==============================================================

-- name: inc_wo_site_down
SELECT
  inc.incident_id AS "Incident ID",
  inc.id AS "Incident Numeric ID",
  CASE inc.status
    WHEN 'in_progress' THEN 'In Progress'
    ELSE INITCAP(REPLACE(inc.status, '_', ' '))
  END AS "Incident Status",
  wo.wo_id AS "INC-WO ID",
  wo.id AS "INC-WO Numeric ID",
  wo.created_at AS "INC-WO Created At",
  CASE wo.status
    WHEN 'in_progress' THEN 'In Progress'
    WHEN 'on_hold' THEN 'On Hold'
    ELSE INITCAP(REPLACE(wo.status, '_', ' '))
  END AS "INC-WO Status",
  wo.resolved_at AS "Resolved At",
  INITCAP(REPLACE(inc.incident_category, '_', ' ')) AS "Incident Category",
  ploc.fra_site_name AS "Site Name",
  COALESCE(sites.standard_code, inc.site_code) AS "Site Code",
  CASE WHEN wo.overdue THEN 'Yes' ELSE 'No' END AS Overdue,
  CASE wo.support_level
    WHEN 'l2_on_site' THEN 'L2 On-Site'
    WHEN 'l3_internal_support' THEN 'L3 Internal Support'
    ELSE INITCAP(REPLACE(wo.support_level, '_', ' '))
  END AS "Support Level",
  team.name AS "Responsible Team",
  wo.fault_description AS "Fault Description",
  sites.hub_site AS "Hub Site",
  INITCAP(sites.site_grade) AS "Site Grade",
  province.name AS "Province",
  district.name AS "District",
  commune.name AS "Commune"
FROM object_324 wo
LEFT JOIN object_322 inc ON wo.parent_incident = inc.id
LEFT JOIN object_310 team ON wo.responsible_team = team.id
LEFT JOIN object_160 sites ON wo.site = sites.id
LEFT JOIN object_162 province
  ON (CASE WHEN sites.id IS NULL THEN inc.province_ref ELSE sites.province END) = province.id
LEFT JOIN object_164 district
  ON (CASE WHEN sites.id IS NULL THEN inc.district ELSE sites.district END) = district.id
LEFT JOIN object_166 commune
  ON (CASE WHEN sites.id IS NULL THEN inc.commune ELSE sites.commune END) = commune.id
LEFT JOIN object_308 ploc ON ploc.id = sites.physical_location
WHERE wo.category = 'site_down'
  AND wo.status NOT IN ('resolved', 'closed')
  AND inc.status != 'closed'
ORDER BY wo.created_at DESC NULLS FIRST;
