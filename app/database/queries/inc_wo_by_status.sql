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
-- "Incident Category" is included so the "Overdue"/"Overdue L2"/"Overdue L3"
-- badges (see app/services/incwo/incwo_service.py's BADGE_FILTERS) can drop
-- just the Customer Complaint-originated INC-WOs whose parent Incident is
-- already Resolved — every other category is kept regardless of resolved
-- status.
--
-- Unlike incident_by_status.sql, no site_text parsing is needed here —
-- INC-WO's own `site` column is a direct integer FK to Site (object_160.id).
-- NMS/Province/District/Commune resolve the same way (through the joined
-- Site), and one row per INC-WO comes for free since this queries
-- object_324 directly (no LATERAL "latest one" needed).
--
-- "Other Site" fallback: an INC-WO's own `site` FK is null whenever its
-- parent Incident is an "Other Site" case (see incident_by_status.sql's
-- COALESCE note) — confirmed live: INC-WO-P-0098795 (parent
-- INC-0000223251) has site=NULL, same as its parent incident. Falls back
-- to the parent Incident's own site_code/province_ref/district/commune
-- (Site Code via COALESCE; Province/District/Commune via a CASE keyed on
-- sites.id IS NULL, not just a blank field, same reasoning as
-- incident_by_status.sql) so these still show a real Site Code/Province/
-- District/Commune instead of blank.
-- ==============================================================

-- name: inc_wo_by_status
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
  INITCAP(REPLACE(inc.incident_category, '_', ' ')) AS "Incident Category",
  ploc.fra_site_name AS "Site Name",
  COALESCE(sites.standard_code, inc.site_code) AS "Site Code",
  CASE WHEN wo.overdue THEN 'Yes' ELSE 'No' END AS Overdue,
  CASE wo.support_level
    WHEN 'l2_on_site' THEN 'L2 On-Site'
    WHEN 'l3_internal_support' THEN 'L3 Internal Support'
    ELSE INITCAP(REPLACE(wo.support_level, '_', ' '))
  END AS "Support Level",
  wo.fault_description AS "Fault Description",
  sites.hub_site AS "Hub Site",
  INITCAP(sites.site_grade) AS "Site Grade",
  province.name AS "Province",
  district.name AS "District",
  commune.name AS "Commune"
FROM object_324 wo
LEFT JOIN object_322 inc ON wo.parent_incident = inc.id
LEFT JOIN object_160 sites ON wo.site = sites.id
LEFT JOIN object_162 province
  ON (CASE WHEN sites.id IS NULL THEN inc.province_ref ELSE sites.province END) = province.id
LEFT JOIN object_164 district
  ON (CASE WHEN sites.id IS NULL THEN inc.district ELSE sites.district END) = district.id
LEFT JOIN object_166 commune
  ON (CASE WHEN sites.id IS NULL THEN inc.commune ELSE sites.commune END) = commune.id
LEFT JOIN object_308 ploc ON ploc.id = sites.physical_location
WHERE wo.status != 'closed'
AND inc.status != 'closed'
ORDER BY wo.created_at DESC NULLS FIRST;
