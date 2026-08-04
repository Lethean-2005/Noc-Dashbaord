-- ==============================================================
-- Per-site radio technology inventory (object_227, the same NE table
-- ne_nms_lookup.sql resolves down to one row per site (oldest by id) for
-- the NMS code. This query keeps every distinct (site, technology) pair
-- instead, since
-- app/services/alarm_site_down/alarm_completely_site_down_service.py needs
-- the site's FULL technology footprint (which of 2g/3g/4g/5g it actually
-- has), not just one representative NE.
--
-- object_227.technology is confirmed (queried directly) to only ever be
-- one of exactly '2g', '3g', '4g', '5g' — lowercase, no other values.
--
-- Excludes off_air sites (same filter site_cache.sql already applies) —
-- without it, a site marked off_air in the master data but still firing
-- alarms on the raw feed (object_138) would still get a technology
-- inventory here, which is enough for classify_site_technology_coverage()
-- to count it as "completely down" and surface it on RAN Site Down/RAN
-- Tech Down/Alarm Completely Site Down, even though it's decommissioned
-- and site_cache itself has no record of it (so its Site Name/Hub/Grade/
-- Province show up blank there too). Confirmed with real data: sites
-- PP6339/PP6967, both status=off_air in object_160, both still had open
-- SRAN alarms and a technology inventory row here.
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
