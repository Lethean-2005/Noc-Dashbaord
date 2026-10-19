-- ==============================================================
-- Site Down incidents for incident_sync_service.py, cached as
-- incident_site_down behind the "Incident Site Down" card. The Telegram
-- Site Down alert reads this same cache directly — Last Comments is
-- included here specifically for that.
--
-- Not incident_by_status (that's scoped to new/in_progress for the
-- dashboard badges) — this follows the source system's own "Incident"
-- filter instead: Category = Site Down, Status != Closed, and Cleared
-- Alarm Received = FALSE (so an incident whose alarm already cleared
-- doesn't count even if the ticket's still open).
--
-- "Occurred At" splits by Source, confirmed by the user: an
-- Alarms-sourced incident's real down-start is issue_occurred_at (the
-- alarm's own detection time); a non-Alarms incident (NOC/Field/
-- Customer Complaint) has no alarm feed behind it, so its own created_at
-- (when the ticket was raised) is the only real "down since" signal.
-- Same source-based split as incident_site_down_restored_by_ids.sql's
-- own "Restored At" column, for the matching restore-side timestamp.
--
-- Same Site/NMS/Province/District/Commune join as incident_by_status.sql
-- — see that file for the join/fallback/batching reasoning.
-- ==============================================================

-- name: incident_site_down
SELECT
  inc.incident_id AS "Incident ID",
  inc.id AS "Incident Numeric ID",
  CASE inc.status
    WHEN 'in_progress' THEN 'In Progress'
    ELSE INITCAP(REPLACE(inc.status, '_', ' '))
  END AS "Incident Status",
  ploc.name AS "Site Name",
  sites.id AS "Site Numeric ID",
  COALESCE(sites.standard_code, inc.site_code) AS "Site Code",
  CASE
    WHEN LOWER(inc.source) = 'alarms' THEN inc.issue_occurred_at
    ELSE inc.created_at
  END AS "Occurred At",
  inc.l1_noc_investigation_result AS "L1 NOC Investigation Result",
  inc.last_comments AS "Last Comments",
  INITCAP(inc.source) AS "Source",
  sites.hub_site AS "Hub Site",
  INITCAP(sites.site_grade) AS "Site Grade",
  province.name AS "Province",
  district.name AS "District",
  commune.name AS "Commune"
FROM object_322 inc
LEFT JOIN LATERAL (
  SELECT DISTINCT
    TRIM(
      REGEXP_REPLACE(
        NULLIF(TRIM(site_part), ''),
        '^[A-Za-z]{2}',
        ''
      )
    ) AS site_code
  FROM UNNEST(STRING_TO_ARRAY(inc.site_text, ',')) AS site_part
) site ON TRUE
LEFT JOIN object_160 sites ON site.site_code = sites.standard_code
LEFT JOIN object_162 province
  ON (CASE WHEN sites.id IS NULL THEN inc.province_ref ELSE sites.province END) = province.id
LEFT JOIN object_164 district
  ON (CASE WHEN sites.id IS NULL THEN inc.district ELSE sites.district END) = district.id
LEFT JOIN object_166 commune
  ON (CASE WHEN sites.id IS NULL THEN inc.commune ELSE sites.commune END) = commune.id
LEFT JOIN object_308 ploc ON ploc.id = sites.physical_location
WHERE inc.incident_category = 'site_down'
  AND inc.status != 'closed'
  AND inc.cleared_alarm_received = FALSE
ORDER BY "Occurred At" DESC NULLS FIRST;
