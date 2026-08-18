-- ==============================================================
-- Every INC-WO belonging to a specific batch of incidents, in ONE
-- round-trip — used by incident_by_status.sql/incident_site_down.sql/
-- vip_incident_status.sql's sync to resolve "latest INC-WO per
-- (incident, site)" without a per-row LATERAL subquery against the
-- foreign object_324 table. No status filter (a Closed WO can still be
-- the latest one); "latest per (incident, site)" is picked in Python
-- afterward — see IncidentSyncService._latest_wo_by_incident_site().
--
-- Responsible Team is the WO's own team (object_310 FK), not the parent
-- Incident's — used to enrich VipAlarmService/MentorSiteService's rows.
-- ==============================================================

-- name: inc_wo_by_incident_ids
SELECT
  wo.parent_incident AS "Incident Numeric ID",
  wo.site AS "Site Numeric ID",
  wo.wo_id AS "INC-WO ID",
  wo.id AS "INC-WO Numeric ID",
  wo.created_at AS "INC-WO Created At",
  CASE wo.status
    WHEN 'in_progress' THEN 'In Progress'
    WHEN 'on_hold' THEN 'On Hold'
    ELSE INITCAP(REPLACE(wo.status, '_', ' '))
  END AS "INC-WO Status",
  wo.resolved_at AS "Resolved At",
  team.name AS "Responsible Team",
  CASE wo.support_level
    WHEN 'l2_on_site' THEN 'L2 On-Site'
    WHEN 'l3_internal_support' THEN 'L3 Internal Support'
    ELSE INITCAP(REPLACE(wo.support_level, '_', ' '))
  END AS "Support Level"
FROM object_324 wo
LEFT JOIN object_310 team ON wo.responsible_team = team.id
WHERE wo.parent_incident = ANY(:incident_ids);
