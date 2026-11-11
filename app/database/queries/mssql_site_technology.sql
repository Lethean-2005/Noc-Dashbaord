-- ==============================================================
-- Per-site radio technology inventory from MSSQL (TBL_NE) — replaces
-- the old Postgres object_227 source for site_technology_cache. TECH
-- is LOWERed to match the cache's existing 2g/3g/4g/5g convention.
-- Note: TBL_NE's TECH only ever contains 2G/4G/5G — no 3G rows exist
-- here.
-- ==============================================================

-- name: site_technology
SELECT DISTINCT
    ne.SITE_CODE AS "Site Code",
    LOWER(ne.TECH) AS "Technology"
FROM TBL_NE ne
INNER JOIN TBL_SITE ts
    ON ts.SITE_CODE = ne.SITE_CODE
    AND ts.STATUS = 'On Air'
    AND ts.IS_REMOVED = 0
WHERE ne.TECH IS NOT NULL
    AND ne.IS_REMOVED = 0
ORDER BY ne.SITE_CODE, LOWER(ne.TECH);
