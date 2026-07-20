-- ==============================================================
-- Site Down incidents — shared by two consumers:
--   - app/services/telegram_alert.py       (queried live, every 4h)
--   - app/services/incident_sync_service.py (cached as incident_site_down,
--                                            behind the "Incident Site Down"
--                                            card on the Custom Dashboard)
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
-- Same Site/INC-WO/NMS/Province/District/Commune join as
-- incident_by_status.sql — see that file for the join reasoning.
-- ==============================================================

-- name: site_down
WITH single_ne AS (
  SELECT
    ne.*,
    ROW_NUMBER() OVER (PARTITION BY ne.site_name ORDER BY ne.id) as rn
  FROM
    object_227 ne
)
SELECT
  inc.incident_id AS "Incident ID",
  CASE inc.status
    WHEN 'in_progress' THEN 'In Progress'
    ELSE INITCAP(REPLACE(inc.status, '_', ' '))
  END AS "Incident Status",
  wo.wo_id AS "INC-WO ID",
  wo.created_at AS "INC-WO Created At",
  CASE wo.status
    WHEN 'in_progress' THEN 'In Progress'
    WHEN 'on_hold' THEN 'On Hold'
    ELSE INITCAP(REPLACE(wo.status, '_', ' '))
  END AS "INC-WO Status",
  sites.fra_site_name AS "Site Name",
  sites.standard_code AS "Site Code",
  inc.issue_occurred_at AS "Occurred At",
  inc.l1_noc_investigation_result AS "L1 NOC Investigation Result",
  CASE sne.nms_name
    WHEN 3 THEN 'ZTE'
    WHEN 5 THEN 'Huawei'
    WHEN 7 THEN 'Nokia'
    ELSE NULL
  END AS "NMS",
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
LEFT JOIN LATERAL (
  SELECT wo.*
  FROM object_324 wo
  WHERE wo.parent_incident = inc.id
  ORDER BY wo.created_at DESC NULLS LAST
  LIMIT 1
) wo ON TRUE
WHERE inc.incident_category = 'site_down'
  AND inc.status != 'closed'
  AND inc.cleared_alarm_received = FALSE
ORDER BY inc.issue_occurred_at DESC NULLS FIRST;
