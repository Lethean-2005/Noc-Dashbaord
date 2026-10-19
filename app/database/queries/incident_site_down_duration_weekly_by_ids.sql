-- ==============================================================
-- Step 2 of 2 for "Site-Down Duration — Weekly Trend" (see
-- incident_site_down_duration_weekly.sql for step 1, which already
-- guarantees every id here is a closed, resolved Site Down incident).
-- Resolves each numeric id to one row PER SITE (a multi-site incident,
-- e.g. site_text = 'KC1835,KC1824', fans out to 2 rows here) — unlike
-- incident_closed_trend_by_ids.sql, which dedupes back down to one row
-- per incident, this deliberately keeps every site row: the point of
-- this card's drilldown is "which site(s) were actually down," not a
-- single representative site.
--
-- Scoped to a specific batch of ids (WHERE inc.id = ANY(:incident_ids)),
-- same pattern as incident_closed_trend_by_ids.sql — safe to join here
-- (unlike step 1's full 30-day scan) since the join only ever touches
-- the handful of rows matching this id list.
--
-- Site resolution mirrors incident_closed_trend_by_ids.sql exactly —
-- "Site Name" is ploc.name (object_308, physical location), NOT
-- object_160.name (confirmed against live data that object_160.name is
-- just the same short code again, e.g. "KC1824", not a real name).
-- ==============================================================

-- name: incident_site_down_duration_weekly_by_ids
SELECT
  inc.id AS "Incident Numeric ID",
  ploc.name AS "Site Name",
  COALESCE(sites.standard_code, inc.site_code) AS "Site Code"
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
LEFT JOIN object_308 ploc ON ploc.id = sites.physical_location
WHERE inc.id = ANY(:incident_ids);
