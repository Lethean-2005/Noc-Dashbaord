-- ==============================================================
-- Site master data (object_160) on PostgreSQL — backs site_cache
-- (SiteCacheRepository / SiteSyncService). Province/District/Commune/
-- Village are resolved to real names via joins, not raw FK ids.
--
-- physical_location_name is object_308.name (ploc) — the Physical
-- Location's own code (e.g. "KAB_SROV_TOCH"), a different thing from
-- the site's own name.
--
-- Curated subset of v_site_master — add a field to SiteCacheRepository.
-- columns and app/database/cache.py's schema too, or it comes back NULL.
-- ==============================================================

-- name: site_cache
SELECT
    sites.id,
    sites.name,
    sites.status,
    sites.type,
    sites.site_grade,
    sites.fra_site_name,
    sites.standard_code,
    sites.site_priority,
    sites.site_strategic_type,
    province.name AS province,
    district.name AS district,
    commune.name AS commune,
    village.name AS village,
    sites.physical_location,
    ploc.name AS physical_location_name,
    ploc.adress AS physical_location_address,
    sites.p_lat,
    sites.p_lon,
    sites.hub_site,
    sites.actual_ran_vendor
FROM object_160 sites
LEFT JOIN object_162 province ON province.id = sites.province
LEFT JOIN object_164 district ON district.id = sites.district
LEFT JOIN object_166 commune ON commune.id = sites.commune
LEFT JOIN object_168 village ON village.id = sites.village
LEFT JOIN object_308 ploc ON ploc.id = sites.physical_location
where sites.status != 'off_air'
ORDER BY sites.id;
