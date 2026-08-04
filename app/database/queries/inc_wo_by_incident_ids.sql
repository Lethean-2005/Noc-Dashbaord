-- ==============================================================
-- Every INC-WO belonging to a specific batch of incidents, in ONE
-- round-trip — used by incident_by_status.sql/incident_site_down.sql/
-- vip_incident_status.sql's sync to resolve "latest INC-WO per
-- (incident, site)" without a per-row LATERAL subquery against the
-- foreign object_324 table (confirmed live via EXPLAIN ANALYZE to cost
-- one remote round-trip PER ROW — ~21ms x 356 rows = ~7.5s for what should
-- be a single query). No status filter here (matches the old LATERAL's
-- behavior exactly — it takes the single latest WO regardless of status,
-- including a Closed one, if that's genuinely the most recent); "latest
-- per (incident, site)" itself is picked in Python afterward — see
-- IncidentSyncService._latest_wo_by_incident_site().
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
  wo.resolved_at AS "Resolved At"
FROM object_324 wo
WHERE wo.parent_incident = ANY(:incident_ids);
