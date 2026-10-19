-- Site Vendor Check — one query to see everything relevant to "what
-- vendor actually runs this site" in one place: the site's
-- actual_ran_vendor code, every NE record for it (oldest first, so you
-- can see if a newer NE disagrees with an older one), and what its own
-- live alarms say the vendor is.
--
-- Replace '1439' below with the site's standard_code (the short site
-- code shown across the dashboard, e.g. "1439", "0723").
--
-- Vendor code legend (two DIFFERENT numbering schemes — don't mix them up):
--   object_227.vendor / object_227.nms_name / ape_alarm.nms -> 3=ZTE, 5=Huawei, 7=Nokia
--   object_160.actual_ran_vendor -> a Counterparty catalog record ID
--     (object_170 / local cache table counterparty_cache — id, name, type).
--     Only 6=ZTE, 7=Nokia, 20=Huawei are confirmed reliable, by an EXACT
--     on-air site-count match against Streamline's own UI filter
--     (Status='On Air' AND Actual RAN Vendor=<name>) — see app/utils/nms.py
--     for the full story. Codes 21 and 22 are ALSO Counterparty records
--     literally named "Huawei" (21: type 'brand', 22: type 'vendor'), but
--     Streamline's own filter doesn't count either of them under
--     "Actual RAN Vendor = Huawei" (confirmed 2026-08-27), so this app
--     doesn't treat them as Huawei either — same display name isn't
--     enough once it disagrees with the real counted behavior. Every
--     other code (5, 58, 115, ...) is unconfirmed; check
--     counterparty_cache (or object_170 directly) for its name/type
--     before trusting it — e.g. 58 = "Other" (not a real vendor at all),
--     115 = "Alcatel" (a real, distinct vendor).
--
-- (An earlier version of this comment said "only 21=Nokia, 22=Huawei
-- confirmed reliable" — that was wrong, based on cross-referencing
-- against ape_alarm.nms, an unreliable signal for this purpose. Left
-- here as a warning, not a citation.)

-- 1) The site itself + its actual_ran_vendor code
SELECT
    standard_code,
    name,
    actual_ran_vendor,
    planned_ran_vendor
FROM object_160
WHERE standard_code = '1439';

-- 2) Every NE (network element) recorded for this site, oldest first —
--    the "lowest id wins" rule elsewhere in this app always picks the
--    FIRST row here, which can be wrong if a newer row (further down)
--    reflects a vendor swap.
SELECT
    ne.id,
    ne.ne_name,
    ne.bts_name,
    ne.technology,
    ne.vendor,
    ne.nms_name,
    ne.nms_id,
    ne.created_at
FROM object_227 ne
JOIN object_160 sites ON sites.id = ne.site_name
WHERE sites.standard_code = '1439'
ORDER BY ne.id;

-- 3) What this site's own real, live alarms say the vendor is — kept
--    for reference, but treat with caution: alarm-derived vendor counts
--    were found (2026-08-27) to disagree with Streamline's own
--    Actual RAN Vendor field for a meaningful share of sites, likely
--    because alarm frequency doesn't track fleet share evenly across
--    vendors — don't use this alone to validate a new actual_ran_vendor
--    code the way an earlier investigation did.
--
--    NOT run against Postgres directly: object_138.site is a raw, messy
--    string (not the clean site code), and turning it back into a site
--    code needs a 6-step regex/lookup chain (see
--    app/utils/get_processed_site.py) — too involved for a one-off
--    manual query, and object_138 is a ~10M-row table prone to
--    "conflict with recovery" if scanned broadly.
--
--    Instead, run this against the LOCAL cache the app already resolved
--    for you — instance/localstorage.db (any SQLite browser, e.g. "DB
--    Browser for SQLite"), table `ape_alarm`, already keyed by the real
--    site_code:
--
--    SELECT DISTINCT site_code, site_name, nms, technology, occurred_at
--    FROM ape_alarm
--    WHERE site_code = '1439'
--    ORDER BY occurred_at DESC;

-- 4) What Streamline itself calls this actual_ran_vendor code — the
--    most authoritative check of all. Either open
--    prd-web-mc.cellcard.com.kh/counterparties_catalog/form/<code>
--    directly in Streamline, or read it from the local cache (already
--    synced, see app/services/site/site_sync_service.py's
--    sync_counterparty()):
--
--    SELECT id, name, type FROM counterparty_cache WHERE id = <code>;
--
--    A matching name is a necessary but NOT sufficient condition to
--    trust a code, though — confirm it against Streamline's own
--    per-vendor on-air site count too (see the legend above for why).
