-- ==============================================================
-- Query for the Site table (object_160) on PostgreSQL
-- ==============================================================

-- name: site_all
SELECT
    id,
    name,
    status,
    type,
    site_grade,
    fra_site_name,
    standard_code,
    site_priority,
    province,
    district,
    commune,
    village,
    physical_location,
    p_lat,
    p_lon,
    hub_site
FROM object_160
ORDER BY id;
