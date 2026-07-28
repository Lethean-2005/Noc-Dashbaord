-- ==============================================================
-- Incident drilldown detail, synced into the local "incident_by_status"
-- cache table (see app/database/cache.py) every INCIDENT_SYNC_INTERVAL_SECONDS
-- — every Incident-column badge (New, New Site-Down, In-Progress,
-- In-Progress Site-Down, Overdue, Overdue Site-Down) filters from this one
-- cached table, since 'overdue' is a flag on top of status, not a separate
-- status value.
--
-- Only status IN ('new', 'in_progress') is cached — that covers every
-- Incident badge on the dashboard; resolved/closed incidents aren't shown
-- on any badge, so there's no reason to sync/store them here.
--
-- Site is matched by stripping the 2-letter province prefix off the first
-- comma-separated part of site_text, then matching that against Site's
-- standard_code (its numeric code) — site_ref/site_code on Incident itself
-- are essentially never populated for alarm-raised incidents.
--
-- NMS Code comes from object_227 (NE - Logical Technology), deduplicated to
-- one row per site (oldest by id) via ROW_NUMBER — the raw code is mapped
-- to a vendor name in Python (app/utils/nms.py's NMS_NAMES), not here, so
-- that mapping lives in one place instead of being copy-pasted into every
-- query that needs it.
--
-- Only the latest INC-WO per incident is kept (LATERAL ... ORDER BY
-- created_at DESC LIMIT 1) so this stays one row per incident, matching
-- primary key incident_id — an incident can have several INC-WO over its
-- lifetime, but the drilldown only needs the current one.
-- ==============================================================

-- name: incident_by_status
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
  inc.issue_occurred_at AS "Occurred At",
  CASE WHEN inc.overdue THEN 'Yes' ELSE 'No' END AS Overdue,
  CASE inc.incident_category
    WHEN 'bss_hardware' THEN 'BSS Hardware'
    WHEN 'bss_software' THEN 'BSS Software'
    WHEN 'oss_platform' THEN 'OSS Platform'
    WHEN 'ip_core' THEN 'IP Core'
    WHEN 'cs_core' THEN 'CS Core'
    WHEN 'ps_core' THEN 'PS Core'
    ELSE INITCAP(REPLACE(inc.incident_category, '_', ' '))
  END AS Category,
  inc.l1_noc_investigation_result AS "L1 NOC Investigation Result",
  sne.nms_name AS "NMS Code",
  sites.hub_site AS "Hub Site",
  INITCAP(sites.site_grade) AS "Site Grade",
  province.name AS "Province",
  district.name AS "District",
  commune.name AS "Commune"
FROM object_322 inc
LEFT JOIN LATERAL (
  SELECT
    TRIM(
      REGEXP_REPLACE(
        NULLIF(TRIM(SPLIT_PART(inc.site_text, ',', 1)), ''),
        '^[A-Za-z]{2}',
        ''
      )
    ) AS site_code
) site ON TRUE
LEFT JOIN object_160 sites ON site.site_code = sites.standard_code
LEFT JOIN single_ne sne ON sites.id = sne.site_name AND sne.rn = 1
LEFT JOIN object_162 province ON sites.province = province.id
LEFT JOIN object_164 district ON sites.district = district.id
LEFT JOIN object_166 commune ON sites.commune = commune.id
LEFT JOIN object_308 ploc ON ploc.id = sites.physical_location
LEFT JOIN LATERAL (
  SELECT wo.*
  FROM object_324 wo
  WHERE wo.parent_incident = inc.id
  ORDER BY wo.created_at DESC NULLS LAST
  LIMIT 1
) wo ON TRUE
WHERE inc.status IN ('new', 'in_progress')
ORDER BY inc.issue_occurred_at DESC NULLS FIRST;
