-- ==============================================================
-- Per-site RAN/SRAN baseband name from TBL_NE — e.g. "NSiKCH1002",
-- the identifier shown as "RAN_NAME" on the Site Down 24h alert's
-- multi-site Excel attachment. A site can have >1 NE row; 15 of
-- ~3772 sites (confirmed live) carry 2 distinct SRAN values for their
-- NEs — rare, not filtered out here (ORDER BY keeps it deterministic),
-- so the first one wins when site_sync_service.py dedupes in Python,
-- same "first-seen per site" convention mssql_site.sql's own sync
-- (mssql_site_onair_sync_service.py) already uses for its own
-- multi-NE-per-site edge case.
-- ==============================================================

-- name: site_ran_name
SELECT
    ne.SITE_CODE AS "Site Code",
    ne.SRAN AS "RAN Name"
FROM TBL_NE ne
INNER JOIN TBL_SITE ts
    ON ts.SITE_CODE = ne.SITE_CODE
    AND ts.STATUS = 'On Air'
    AND ts.IS_REMOVED = 0
WHERE ne.SRAN IS NOT NULL
    AND ne.IS_REMOVED = 0
ORDER BY ne.SITE_CODE;
