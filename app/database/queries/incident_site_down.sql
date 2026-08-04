-- ==============================================================
-- Site Down incidents — for app/services/incident/incident_sync_service.py, cached
-- as incident_site_down behind the "Incident Site Down" card on the
-- Custom Dashboard. The Telegram Site Down alert
-- (app/services/telegram/telegram_alert.py) reads this same cache table
-- directly instead of querying Postgres a second time — Last Comments is
-- included here (rather than only on a separate copy) specifically so the
-- alert can read it from here.
--
-- Not the incident_by_status cache, because that cache is deliberately
-- scoped to status IN ('new', 'in_progress') for the dashboard's Incident
-- badges, but the correct definition here (per the source system's own
-- "Incident" filter) is broader:
--   Incident Category = Site Down
--   AND Status is not Closed          (so a Resolved-but-not-Closed incident
--                                      still counts if its alarm hasn't cleared)
--   AND Cleared Alarm Received = FALSE (an incident whose alarm already
--                                      cleared shouldn't count even if the
--                                      ticket itself is still open)
--
-- Same Site/NMS/Province/District/Commune join as incident_by_status.sql —
-- see that file for the join reasoning, including why site_text is split
-- into one row per site instead of taking only the first one. The "latest
-- INC-WO per (incident, site)" is resolved the same batched way
-- incident_by_status.sql now uses — see that file's header for why (a
-- per-row LATERAL against the foreign object_324 table was ~100x slower).
-- ==============================================================

-- name: incident_site_down
SELECT
  inc.incident_id AS "Incident ID",
  inc.id AS "Incident Numeric ID",
  CASE inc.status
    WHEN 'in_progress' THEN 'In Progress'
    ELSE INITCAP(REPLACE(inc.status, '_', ' '))
  END AS "Incident Status",
  ploc.fra_site_name AS "Site Name",
  sites.id AS "Site Numeric ID",
  sites.standard_code AS "Site Code",
  inc.issue_occurred_at AS "Occurred At",
  inc.l1_noc_investigation_result AS "L1 NOC Investigation Result",
  inc.last_comments AS "Last Comments",
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
LEFT JOIN object_162 province ON sites.province = province.id
LEFT JOIN object_164 district ON sites.district = district.id
LEFT JOIN object_166 commune ON sites.commune = commune.id
LEFT JOIN object_308 ploc ON ploc.id = sites.physical_location
WHERE inc.incident_category = 'site_down'
  AND inc.status != 'closed'
  AND inc.cleared_alarm_received = FALSE
ORDER BY inc.issue_occurred_at DESC NULLS FIRST;
