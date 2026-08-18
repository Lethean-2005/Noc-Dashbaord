-- ==============================================================
-- INC-WO drilldown detail, synced into inc_wo_by_status every
-- INCIDENT_SYNC_INTERVAL_SECONDS — every INC-WO badge (see
-- incwo_service.py's BADGE_FILTERS) filters from this one cached table.
-- Only wo.status != 'closed' rows are kept.
--
-- Resolved Incident + Customer Complaint rows are dropped here: that
-- combination never matches any badge (see BADGE_FILTERS'
-- _is_resolved_customer_complaint), so caching them is dead weight.
-- Every other category keeps its Resolved-incident rows normally.
--
-- "Other Site" fallback: when an INC-WO's own `site` FK is null (its
-- parent Incident is an "Other Site" case), Site Code/Province/District/
-- Commune fall back to the parent Incident's own values instead of blank.
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
WHERE wo.status != 'closed'
AND inc.status != 'closed'
AND NOT (inc.status = 'resolved' AND inc.incident_category = 'customer_complaint')
ORDER BY wo.created_at DESC NULLS FIRST;
