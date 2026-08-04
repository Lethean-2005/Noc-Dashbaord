-- ==============================================================
-- Site -> NMS vendor code, resolved ONCE here instead of being
-- recomputed independently inside 6 other query files
-- (incident_by_status.sql, inc_wo_by_status.sql, inc_wo_site_down.sql,
-- inc_wo_resolved.sql, incident_site_down.sql, vip_incident_status.sql),
-- each of which used to run its own `single_ne`/`sne` window function over
-- the entire object_227 table just to resolve one column. Same DISTINCT ON
-- (site, lowest id wins) tie-break rule those used, just computed once and
-- cached locally — see app/services/site/site_sync_service.py's
-- sync_ne_nms().
-- ==============================================================

-- name: ne_nms_lookup
SELECT DISTINCT ON (sites.standard_code)
  sites.standard_code AS "Site Code",
  ne.nms_name AS "NMS Code"
FROM object_227 ne
JOIN object_160 sites ON sites.id = ne.site_name
ORDER BY sites.standard_code, ne.id;
