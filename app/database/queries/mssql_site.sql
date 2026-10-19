-- ==============================================================
-- Site master data from MSSQL (TBL_SITE joined to TBL_NE for VENDOR) —
-- On Air sites only. Separate from Postgres's site_cache (object_160):
-- this is a different source system with its own SITE_CODE scheme (3,668
-- of 3,716 codes overlap with site_cache's standard_code — confirmed
-- 2026-08-28), no "planned"/"ready_for_installation" status (TBL_SITE
-- only has On Air/Off Air), and no hub_site field at all.
--
-- ne.IS_REMOVED = 0 + DISTINCT: a site can have several NEs (radios), but
-- every real site's NEs agree on one VENDOR (confirmed 2026-08-28 — the
-- only multi-vendor group found was junk rows with SITE_CODE NULL, which
-- INNER JOIN already drops), so this stays one row per site rather than
-- fanning out per NE.
-- ==============================================================

-- name: site_onair
SELECT DISTINCT
    ts.SITE_CODE,
    ts.SITE_NAME,
    ts.STATUS,
    ts.PROVINCE,
    ts.DISTRICT,
    ts.VILLAGE,
    ts.LAT,
    ts.LONG,
    ts.BTS_ROOM,
    ts.LINK_TYPE,
    ts.SITE_GRADE,
    ts.SITE_TYPE,
    ts.LOCATION,
    ne.VENDOR
FROM TBL_SITE ts
INNER JOIN TBL_NE ne
    ON ne.SITE_CODE = ts.SITE_CODE
    AND ne.IS_REMOVED = 0
WHERE ts.STATUS = 'On Air'
    AND ts.IS_REMOVED = 0
ORDER BY ts.SITE_CODE;
