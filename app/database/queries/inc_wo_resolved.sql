-- ==============================================================
-- "INC-WO Resolved" card (reports/index.html), synced into
-- inc_wo_resolved every INCIDENT_SYNC_INTERVAL_SECONDS. INNER JOINs on
-- inc.status = 'in_progress' (Resolved WO, parent Incident still open) —
-- unlike the LEFT JOINs in inc_wo_by_status.sql/inc_wo_site_down.sql.
--
-- Deliberately NOT filtered here to "every WO on this incident is
-- resolved" — that needs comparing against sibling WOs of every status,
-- which would mean joining/subquerying object_324 (100k+ rows) on this
-- replica, measurably widening exposure to its "conflict with recovery"
-- cancellations (see ape_alarm.sql's own note on the same tradeoff, and
-- git history on this file — that approach was tried and reverted).
-- That same-incident-fully-resolved check is done in Python instead,
-- in IncWoService.get_resolved_details() (incwo_service.py), against
-- the already-synced inc_wo_by_status cache — no extra DB round trip.
-- ==============================================================

-- name: inc_wo_resolved
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
  ploc.name AS "Site Name",
  COALESCE(sites.standard_code, inc.site_code) AS "Site Code",
  CASE WHEN wo.overdue THEN 'Yes' ELSE 'No' END AS Overdue,
  CASE wo.support_level
    WHEN 'l2_on_site' THEN 'L2 On-Site'
    WHEN 'l3_internal_support' THEN 'L3 Internal Support'
    ELSE INITCAP(REPLACE(wo.support_level, '_', ' '))
  END AS "Support Level",
  team.name AS "Responsible Team",
  wo.fault_description AS "Fault Description",
  wo.resolution AS "Resolution",
  sites.hub_site AS "Hub Site",
  INITCAP(sites.site_grade) AS "Site Grade",
  province.name AS "Province",
  district.name AS "District",
  commune.name AS "Commune"
FROM object_324 wo
JOIN object_322 inc ON wo.parent_incident = inc.id AND inc.status = 'in_progress'
LEFT JOIN object_310 team ON wo.responsible_team = team.id
LEFT JOIN object_160 sites ON wo.site = sites.id
LEFT JOIN object_162 province
  ON (CASE WHEN sites.id IS NULL THEN inc.province_ref ELSE sites.province END) = province.id
LEFT JOIN object_164 district
  ON (CASE WHEN sites.id IS NULL THEN inc.district ELSE sites.district END) = district.id
LEFT JOIN object_166 commune
  ON (CASE WHEN sites.id IS NULL THEN inc.commune ELSE sites.commune END) = commune.id
LEFT JOIN object_308 ploc ON ploc.id = sites.physical_location
WHERE wo.status = 'resolved'
ORDER BY wo.created_at DESC NULLS FIRST;
