-- ==============================================================
-- VIP / VVIP Site master data from MSSQL (SITE_INFO)
-- ==============================================================

-- name: vip_site_cache
SELECT ID, SITE_CODE, SITE_NAME, BTS_NAME, VIP, PROVINCE, DISTRICT, COMMUNE,
       VILLAGE, LOCATION, SITE_GRADE, ON_AIR, PRODUCT, TECH, SITE_ID, LAT, LONG
FROM SITE_INFO
WHERE VIP IN ('VIP', 'VVIP');
