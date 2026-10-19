-- ==============================================================
-- VIP / VVIP Site master data from MSSQL (TBL_SITE + TBL_NE)
-- ==============================================================

-- name: vip_site_cache
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
    ts.SITE_STRATEGIC,
    ne.VENDOR
FROM TBL_SITE ts
INNER JOIN TBL_NE ne
    ON ne.SITE_CODE = ts.SITE_CODE
    AND ne.IS_REMOVED = 0
WHERE ts.STATUS = 'On Air'
    AND ts.IS_REMOVED = 0
    AND ts.SITE_STRATEGIC IN ('VIP', 'VVIP')
ORDER BY ts.SITE_CODE;
