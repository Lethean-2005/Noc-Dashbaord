-- ==============================================================
-- Per-site radio technology inventory (object_227) — keeps every
-- distinct (site, technology) pair, unlike ne_nms_lookup.sql's one-row-
-- per-site, since alarm_completely_site_down_service.py needs a site's
-- full technology footprint (2g/3g/4g/5g), not just one NE.
--
-- Excludes off_air sites (same as site_cache.sql) — without it, a site
-- marked off_air but still firing alarms on the raw feed would count as
-- "completely down" and wrongly surface on RAN Site Down/Tech Down —
-- confirmed live with PP6339/PP6967, both off_air with open SRAN alarms.
-- ==============================================================

-- name: site_technology_cache
SELECT DISTINCT
  sites.standard_code AS "Site Code",
  ne.technology AS "Technology"
FROM object_227 ne
JOIN object_160 sites ON sites.id = ne.site_name
WHERE ne.technology IS NOT NULL
  AND sites.status != 'off_air'
ORDER BY sites.standard_code, ne.technology;
