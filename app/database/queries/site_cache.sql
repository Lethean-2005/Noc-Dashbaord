-- ==============================================================
-- Site master data (object_160) on PostgreSQL — backs the local
-- site_cache table (SiteCacheRepository / SiteSyncService).
--
-- Province/District/Commune/Village are resolved to their real names
-- here via the same joins the source system's own v_site_master view
-- uses (object_162/164/166/168), instead of leaving them as raw FK ids.
--
-- object_160.name is the site's real, always-populated name (e.g.
-- "KD5977" — confirmed 0% blank across all 4,757 sites). fra_site_name
-- is cached too (blank for ~10.7% of sites).
--
-- object_308 (joined as ploc) is the Physical Location a site sits at —
-- physical_location_name is a different thing entirely from the site's
-- own name (e.g. site "KD5977" sits at physical location "KD148"). Pulled
-- from ploc.fra_site_name rather than ploc.name — object_308's own
-- fra_site_name is reliably populated (blank for only 0.2% of physical
-- locations), unlike object_160.fra_site_name above.
--
-- This is a curated subset of the source system's full v_site_master
-- view (~100 columns — lease/permit/audit/grid fields, etc.) — every
-- column selected here has a matching name in SiteCacheRepository.columns
-- and app/database/cache.py's site_cache schema; add a field to all
-- three together, not just here, or it'll silently come back as NULL.
-- ==============================================================

-- name: site_all
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
    ploc.fra_site_name AS physical_location_name,
    ploc.adress AS physical_location_address,
    sites.p_lat,
    sites.p_lon,
    sites.hub_site
FROM object_160 sites
LEFT JOIN object_162 province ON province.id = sites.province
LEFT JOIN object_164 district ON district.id = sites.district
LEFT JOIN object_166 commune ON commune.id = sites.commune
LEFT JOIN object_168 village ON village.id = sites.village
LEFT JOIN object_308 ploc ON ploc.id = sites.physical_location
where sites.status != 'off_air'
ORDER BY sites.id;
