-- ==============================================================
-- Here is a Query of MSSQL for ISP POP / EZE / TCT cards ---
-- ===============================================================

-- name: isp_pop_active
SELECT p.AlarmName, pop.NAME AS pop_name, pop.NCODE AS pop_code,
       p.DeviceName, p.IPAddress, p.DownTime, p.RestoredTime,
       p.Status, pop.Province, p.PROBLEM_DETAILS, p.NOTE,
       p.INTERFACE, p.RTID, p.SourceGroup, p.ADD_INFO
FROM noc.TBL_PPD p
LEFT JOIN noc.TBL_ISPDEV isp ON p.IPAddress = isp.IP
LEFT JOIN noc.TBL_POP pop   ON isp.CODE   = pop.NCODE
WHERE p.AlarmName IN ('POP/PON DOWN', 'POP/PON POWER')
  AND (p.Status = 1 OR p.RestoredTime IS NULL)
  AND pop.NAME IS NOT NULL AND pop.NCODE IS NOT NULL;

-- name: eze_active
SELECT p.AlarmName, SUBSTRING(p.AlarmName, 5, 200) AS alarm_type,
       p.DeviceName, p.IPAddress, p.DownTime, p.RestoredTime, p.Status,
       p.PROBLEM_DETAILS, p.NOTE, p.INTERFACE, p.RTID, p.SourceGroup, p.ADD_INFO,
       pop.NAME AS pop_name, pop.NCODE AS pop_code, pop.Province
FROM noc.TBL_PPD p
LEFT JOIN noc.TBL_ISPDEV isp ON p.IPAddress = isp.IP
LEFT JOIN noc.TBL_POP pop   ON isp.CODE   = pop.NCODE
WHERE p.AlarmName LIKE 'EZE%' AND (p.Status = 1 OR p.RestoredTime IS NULL);

-- name: tct_active
SELECT p.AlarmName, LOWER(SUBSTRING(p.AlarmName, 5, 200)) AS alarm_type,
       p.DeviceName, p.IPAddress, p.DownTime, p.RestoredTime, p.Status,
       p.PROBLEM_DETAILS, p.NOTE, p.INTERFACE, p.RTID, p.SourceGroup, p.ADD_INFO,
       pop.NAME AS pop_name, pop.NCODE AS pop_code, pop.Province
FROM noc.TBL_PPD p
LEFT JOIN noc.TBL_ISPDEV isp ON p.IPAddress = isp.IP
LEFT JOIN noc.TBL_POP pop   ON isp.CODE   = pop.NCODE
WHERE p.AlarmName LIKE 'TCT%' AND (p.Status = 1 OR p.RestoredTime IS NULL);

-- name: it_node_active
-- IT_NODE alarms have no DeviceName/IPAddress (always blank), so there's
-- nothing to join against TBL_ISPDEV/TBL_POP — this is IT infrastructure
-- monitoring (e.g. "Dell R720: No SNMP data collection"), unrelated to POP
-- sites, unlike the other 3 alarm types above.
SELECT AlarmName, DownTime, RestoredTime, Status,
       PROBLEM_DETAILS, NOTE, INTERFACE, RTID, SourceGroup, ADD_INFO
FROM noc.TBL_PPD
WHERE AlarmName = 'IT_NODE' AND (Status = 1 OR RestoredTime IS NULL);
