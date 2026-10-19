-- ==============================================================
-- Every INC-WO for a batch of incidents in one round-trip — resolves
-- "latest INC-WO per (incident, site)" without a per-row LATERAL
-- subquery. No status filter; "latest" is picked in Python afterward
-- (IncidentSyncService._latest_wo_by_incident_site()).
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
