-- ==============================================================
-- POP master data from MSSQL (noc.TBL_POP) — same table alarms.sql
-- already joins against for pop_name/pop_code/province, mirrored here
-- in full for its own local cache.
-- ==============================================================

-- name: pop_cache
SELECT ID, NAME, CODE, OWNER, OWNER_CODE, LAT, LONG, PROVINCE, DISTRICT,
       COMMUNE, LOCATION, TYPE, NETWORK_TYPE, CON_NAME, CON_NUM,
       PRE_OWNER, PRO_OWNER, REMARK, IS_REMOVED, CD, MD, AIRCON, EDC, DG,
       SOLAR, RECTIFIER, INVERTER, UPS, COLOCATED, ACTIVE, CUS, NCODE,
       BACKUP_STATUS
FROM noc.TBL_POP
WHERE IS_REMOVED = 0 OR IS_REMOVED IS NULL;
