-- ==============================================================
-- INC-WO Resolved — for the "INC-WO Resolved" card on the Custom
-- Dashboard (reports/index.html), synced into the local
-- "inc_wo_resolved" cache table (see app/database/cache.py) every
-- INCIDENT_SYNC_INTERVAL_SECONDS.
--
-- Every INC-WO that's Resolved, whose parent Incident is still
-- In-Progress overall (the incident itself isn't fully closed out yet,
-- even though this particular work order is done) — hence the INNER JOIN
-- with inc.status = 'in_progress' baked into the join condition, unlike
-- the LEFT JOINs used in incwo_by_status.sql/incwo_site_down.sql.
-- ==============================================================

-- name: inprogress_wo_resolve
WITH single_ne AS (
  SELECT
    ne.*,
    ROW_NUMBER() OVER (PARTITION BY ne.site_name ORDER BY ne.id) as rn
  FROM
    object_227 ne
)
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
JOIN object_322 inc ON wo.parent_incident = inc.id AND inc.status = 'in_progress'
LEFT JOIN object_160 sites ON wo.site = sites.id
LEFT JOIN single_ne sne ON sites.id = sne.site_name AND sne.rn = 1
LEFT JOIN object_162 province ON sites.province = province.id
LEFT JOIN object_164 district ON sites.district = district.id
LEFT JOIN object_166 commune ON sites.commune = commune.id
LEFT JOIN object_308 ploc ON ploc.id = sites.physical_location
WHERE wo.status = 'resolved'
ORDER BY wo.created_at DESC NULLS FIRST;
