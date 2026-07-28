-- ==============================================================
-- INC-WO drilldown detail, synced into the local "inc_wo_by_status" cache
-- table (see app/database/cache.py) every INCIDENT_SYNC_INTERVAL_SECONDS —
-- every INC-WO-column badge (New, Assigned, Acknowledged, In-Progress,
-- Resolved, Reopened, Returned, On-Hold, Overdue, Overdue L2, Overdue L3)
-- filters from this one cached table; 'overdue'/'support_level' are flags
-- on top of status, not separate status values.
--
-- Only wo.status != 'closed' is cached — closed work orders aren't shown
-- on any badge.
--
-- Unlike incident_by_status.sql, no site_text parsing is needed here —
-- INC-WO's own `site` column is a direct integer FK to Site (object_160.id).
-- NMS/Province/District/Commune resolve the same way (through the joined
-- Site), and one row per INC-WO comes for free since this queries
-- object_324 directly (no LATERAL "latest one" needed).
-- ==============================================================

-- name: incwo_by_status
WITH single_ne AS (
  SELECT
    ne.*,
    ROW_NUMBER() OVER (PARTITION BY ne.site_name ORDER BY ne.id) as rn
  FROM
    object_227 ne
)
SELECT
  COALESCE(inc.incident_id, wo.parent_incident::TEXT) AS "Incident ID",
  COALESCE(inc.id, wo.parent_incident) AS "Incident Numeric ID",
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
  ploc.fra_site_name AS "Site Name",
  sites.standard_code AS "Site Code",
  CASE WHEN wo.overdue THEN 'Yes' ELSE 'No' END AS Overdue,
  CASE wo.support_level
    WHEN 'l2_on_site' THEN 'L2 On-Site'
    WHEN 'l3_internal_support' THEN 'L3 Internal Support'
    ELSE INITCAP(REPLACE(wo.support_level, '_', ' '))
  END AS "Support Level",
  wo.fault_description AS "Fault Description",
  sne.nms_name AS "NMS Code",
  sites.hub_site AS "Hub Site",
  INITCAP(sites.site_grade) AS "Site Grade",
  province.name AS "Province",
  district.name AS "District",
  commune.name AS "Commune"
FROM object_324 wo
LEFT JOIN object_322 inc ON wo.parent_incident = inc.id
LEFT JOIN object_160 sites ON wo.site = sites.id
LEFT JOIN single_ne sne ON sites.id = sne.site_name AND sne.rn = 1
LEFT JOIN object_162 province ON sites.province = province.id
LEFT JOIN object_164 district ON sites.district = district.id
LEFT JOIN object_166 commune ON sites.commune = commune.id
LEFT JOIN object_308 ploc ON ploc.id = sites.physical_location
WHERE wo.status != 'closed'
AND inc.status != 'closed'
ORDER BY wo.created_at DESC NULLS FIRST;
