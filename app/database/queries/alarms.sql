-- ==============================================================
-- Here is a Query of MSSQL for ISP POP / EZE / TCT cards ---
-- ===============================================================

-- name: isp_pop_alarm_cache
-- pop.PRO_OWNER (same column pop_cache/the Map page's own
-- pro_owner-based coloring already reads from noc.TBL_POP directly —
-- see pop.sql) is the one owner-distinguishing field this query needs:
-- unlike EZE/TCT (each already scoped to a single owner), ISP POP mixes
-- Telcotech- and Ezecom-owned sites in the same card/drilldown, so the
-- drilldown table colors each row's Owner cell by this value.
SELECT p.ID, p.AlarmName, pop.NAME AS pop_name, pop.NCODE AS pop_code,
       p.DeviceName, p.IPAddress, p.DownTime, p.RestoredTime,
       p.Status, pop.Province, pop.PRO_OWNER AS pro_owner, p.PROBLEM_DETAILS, p.NOTE,
       p.INTERFACE, p.RTID, p.SourceGroup, p.ADD_INFO,
       p.ACK, p.AB, p.MB, p.MD
FROM noc.TBL_PPD p
LEFT JOIN noc.TBL_ISPDEV isp ON p.IPAddress = isp.IP
LEFT JOIN noc.TBL_POP pop   ON isp.CODE   = pop.NCODE
WHERE p.AlarmName IN ('POP/PON DOWN', 'POP/PON POWER')
  AND (p.Status = 1 OR p.RestoredTime IS NULL)
  AND pop.NAME IS NOT NULL AND pop.NCODE IS NOT NULL;

-- name: eze_alarm_cache
SELECT p.ID, p.AlarmName, SUBSTRING(p.AlarmName, 5, 200) AS alarm_type,
       p.DeviceName, p.IPAddress, p.DownTime, p.RestoredTime, p.Status,
       p.PROBLEM_DETAILS, p.NOTE, p.INTERFACE, p.RTID, p.SourceGroup, p.ADD_INFO,
       p.ACK, p.AB, p.MB, p.MD,
       pop.NAME AS pop_name, pop.NCODE AS pop_code, pop.Province
FROM noc.TBL_PPD p
LEFT JOIN noc.TBL_ISPDEV isp ON p.IPAddress = isp.IP
LEFT JOIN noc.TBL_POP pop   ON isp.CODE   = pop.NCODE
WHERE p.AlarmName LIKE 'EZE%' AND (p.Status = 1 OR p.RestoredTime IS NULL);

-- name: tct_alarm_cache
SELECT p.ID, p.AlarmName, LOWER(SUBSTRING(p.AlarmName, 5, 200)) AS alarm_type,
       p.DeviceName, p.IPAddress, p.DownTime, p.RestoredTime, p.Status,
       p.PROBLEM_DETAILS, p.NOTE, p.INTERFACE, p.RTID, p.SourceGroup, p.ADD_INFO,
       p.ACK, p.AB, p.MB, p.MD,
       pop.NAME AS pop_name, pop.NCODE AS pop_code, pop.Province
FROM noc.TBL_PPD p
LEFT JOIN noc.TBL_ISPDEV isp ON p.IPAddress = isp.IP
LEFT JOIN noc.TBL_POP pop   ON isp.CODE   = pop.NCODE
WHERE p.AlarmName LIKE 'TCT%' AND (p.Status = 1 OR p.RestoredTime IS NULL);

-- name: congestion_history
-- Same shape as tct_alarm_cache above, scoped to just the 2 raw alarm
-- types the "Congestion" badge merges (AlarmService.get_tct_counts()),
-- but WITHOUT the active-only filter — this must include cleared/
-- historical rows too (unlike every other query in this file), which
-- is the whole point: tct_alarm_cache's own replace_all() wipes a
-- congestion alarm out the moment it clears, so there's nowhere else
-- in this app any Congestion history survives. The date floor below is
-- a Python-computed `since` string, not MSSQL GETDATE(), matching this
-- app's own convention of doing date math app-side.
--
-- The explicit `AlarmName LIKE 'TCT%'` below matters on its own, not
-- just as belt-and-suspenders with the SUBSTRING match that follows:
-- EZE's own EZE_TYPES tuple (alarm_service.py) ALSO includes a raw
-- "BANDWIDTH" alarm type, in the same "<PREFIX>_<type>" naming shape
-- TCT uses — so an "EZE_BANDWIDTH" row's own LOWER(SUBSTRING(...)) is
-- "bandwidth" too, and without this extra filter it was being swept
-- into what's supposed to be TCT's own Congestion history (confirmed
-- live: 5 real EZE-prefixed rows turned up in a 9434-row sync before
-- this fix).
--
-- The ('bandwidth', 'congestion') list below is a hardcoded copy of
-- alarm_service.py's CONGESTION_TCT_TYPES — this file can't import that
-- Python tuple, so if that constant ever changes (new type merged into
-- Congestion, a rename, etc.) this line must be updated by hand too.
-- test_alarm_service.py only guards that CONGESTION_TCT_TYPES stays a
-- subset of TCT_TYPES; it can't reach into this .sql file, so there is
-- no automatic check that the two stay in sync with each other.
--
-- (Careful: this query's own comments must never contain a literal
-- "percent s" — load_queries() hands the WHOLE query text, comments
-- included, straight to pymssql, which counts every such occurrence as
-- its own bind placeholder; one turning up in a comment here once
-- caused a real "more placeholders in sql than params available"
-- failure.)
SELECT p.ID, p.AlarmName, LOWER(SUBSTRING(p.AlarmName, 5, 200)) AS alarm_type,
       p.DeviceName, p.IPAddress, p.DownTime, p.RestoredTime, p.Status,
       p.PROBLEM_DETAILS, p.NOTE, p.INTERFACE, p.RTID, p.SourceGroup, p.ADD_INFO,
       p.ACK, p.AB, p.MB, p.MD,
       pop.NAME AS pop_name, pop.NCODE AS pop_code, pop.Province
FROM noc.TBL_PPD p
LEFT JOIN noc.TBL_ISPDEV isp ON p.IPAddress = isp.IP
LEFT JOIN noc.TBL_POP pop   ON isp.CODE   = pop.NCODE
WHERE p.AlarmName LIKE 'TCT%'
  AND LOWER(SUBSTRING(p.AlarmName, 5, 200)) IN ('bandwidth', 'congestion')
  AND p.DownTime >= %s;

-- name: it_node_alarm_cache
-- IT_NODE alarms are IT infrastructure monitoring (e.g. "Dell R720: No SNMP
-- data collection"), unrelated to POP sites, so there's nothing to join
-- against TBL_ISPDEV/TBL_POP here unlike the other 3 alarm types above.
--
-- DeviceName/IPAddress ARE populated for this alarm type (~53.6% of the
-- time, confirmed against 1,715 historical rows) — a previous version of
-- this comment wrongly assumed they were always blank. PROBLEM_DETAILS and
-- INTERFACE are still left out — always blank (0% populated) for IT_NODE;
-- PROBABLE_CAUSE, SourceGroup, and ADD_INFO are the fields that actually
-- carry data. RTID is also left out (IT_NODE has no TT/INC-WOID column in
-- the drilldown).
--
-- ID/NOTE/ACK/AB/MB/MD are included (NOTE starts blank for IT_NODE, same as
-- any alarm before its first Acknowledge) so the three-dot Action menu
-- (Acknowledge/Modify Note + Clear Alarm) works here the same as ISP
-- POP/EZE/TCT — ID in particular is required to identify which single row
-- an Ack/Clear submit should update.
SELECT ID, AlarmName, DeviceName, IPAddress, DownTime, RestoredTime, Status,
       PROBABLE_CAUSE, SourceGroup, ADD_INFO, NOTE, ACK, AB, MB, MD
FROM noc.TBL_PPD
WHERE AlarmName = 'IT_NODE' AND (Status = 1 OR RestoredTime IS NULL);

-- name: acknowledge_note
-- Writes the Acknowledge/Modify popup's Note (already formatted as
-- "TT/INC-WOID: note text" by the caller) back to the real MSSQL row —
-- the only write-back to a source database anywhere in this app; every
-- other query here is read-only. ACK/AB are set only the first time a row
-- is ever acknowledged (ACK starts NULL) and never touched again; MD/MB
-- are set on every edit after that. All four CASE expressions read ACK's
-- pre-update value (SQL Server evaluates every expression in a SET clause
-- against the row's original values, not each other's newly-set values),
-- so this single statement is safe even if two staff submit for the same
-- row at nearly the same moment — whichever UPDATE commits second still
-- sees a consistent one-or-the-other outcome, never a mix of "first-ack"
-- and "later-edit" behavior in one write.
--
-- Matched by ID (the real uniqueidentifier primary key), NOT RTID —
-- confirmed live that RTID repeats across completely unrelated rows (same
-- RTID shared by an EZE_PORT alarm, a POP/PON DOWN alarm, and a POP/PON
-- POWER alarm on different devices), so filtering on RTID instead silently
-- updated 4 unrelated rows (including already-resolved ones) instead of
-- the 1 intended row when this was first tried. NOTE: never write a
-- literal "percent s" placeholder-looking sequence in a comment in this
-- file — pymssql's param substitution scans the whole raw query text
-- including comments, not just executable SQL, so a stray one here throws
-- off the real placeholder count below.
--
-- @Now captured once and reused in both CASE branches — not two separate
-- GETDATE() calls — so ACK and MD can never end up a few milliseconds
-- apart from each other for the exact same write. The trailing SELECT
-- (same round trip, same statement batch) hands back this row's final
-- NOTE/ACK/AB/MD/MB straight to the caller, so AlarmSyncService can patch
-- just this one row into the local cache directly instead of re-fetching
-- the whole table from MSSQL only to refresh the single row this write
-- already touched.
DECLARE @Now datetime2 = GETDATE();

UPDATE noc.TBL_PPD
SET NOTE = %s,
    ACK = CASE WHEN ACK IS NULL THEN @Now ELSE ACK END,
    AB  = CASE WHEN ACK IS NULL THEN %s ELSE AB END,
    MD  = CASE WHEN ACK IS NOT NULL THEN @Now ELSE MD END,
    MB  = CASE WHEN ACK IS NOT NULL THEN %s ELSE MB END
WHERE ID = %s;

SELECT NOTE, ACK, AB, MD, MB FROM noc.TBL_PPD WHERE ID = %s;

-- name: clear_alarm
-- Manually marks a row cleared, for the three-dot Action menu's "Clear
-- Alarm" option (drilldown/_alarm_action_menu.html) on the EZE / TCT /
-- ISP POP tables. Status is a plain bit column — confirmed live
-- (read-only check against real rows) that every row with a real
-- RestoredTime already has Status=False, and Status is never anything but
-- True/False — so setting both together here reproduces exactly what
-- happens when the source device clears the alarm itself, just triggered
-- by a person instead.
--
-- WHERE also requires RestoredTime IS NULL, so this can only ever clear a
-- row that's genuinely still open — if the real device already cleared it
-- between page load and this submit, rowcount comes back 0 and nothing
-- gets overwritten (same "0 rows affected" convention as
-- acknowledge_note above). Matched by ID (the real uniqueidentifier
-- primary key), NOT RTID — same reasoning as acknowledge_note.
UPDATE noc.TBL_PPD
SET Status = 0,
    RestoredTime = GETDATE(),
    MD = GETDATE(),
    MB = %s
WHERE ID = %s AND RestoredTime IS NULL;
