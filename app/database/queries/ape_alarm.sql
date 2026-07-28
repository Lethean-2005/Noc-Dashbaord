-- ==============================================================
-- ALL alarm types (no event_name filter) opened on object_138 — `site`/
-- `additional_info` are selected raw instead of calling Postgres's
-- get_processed_site() PL/pgSQL function on every row. That function ran
-- once per row inside the SELECT (regex matching plus, for some rows, a
-- site_lookup_mv lookup) — a procedural per-row call is expensive on
-- Postgres and made this query run measurably longer than a plain column
-- read, which increases exposure to "conflict with recovery" (the longer
-- a query runs against this replica, the more likely it collides with WAL
-- replay). app/utils/get_processed_site.py ports the exact same 5-step logic to
-- Python, computed locally at normalize time instead — using the
-- site_lookup_cache table (mirrors site_lookup_mv, synced by
-- app/services/site/site_lookup_sync_service.py) for the sran_id/nodeb_id/
-- bts_id lookups the Postgres function did internally.
--
-- Deduped: a single site can fire the same event repeatedly (e.g. "DG on
-- Alarm" many times a day) — ROW_NUMBER() keeps only the latest occurrence
-- per (site, event_name) pair, and Occurrence Count records how many times
-- it fired even though only the newest is kept. Without this, the same
-- ongoing issue would show up as hundreds/thousands of near-identical
-- rows instead of one clean row — this cuts both the row count and the
-- amount of data actually written to the local cache.
--
-- A per-event-type exception for "cell" events (skip dedup so multiple
-- different cells failing at once don't collapse into one row) was tried
-- and reverted: real data showed some cell events repeat at extremely
-- high frequency (1,000+ times for a single site/event), so skipping
-- dedup for them recreated exactly the "thousands of near-identical rows"
-- problem this dedup exists to prevent — same root issue as before, just
-- shifted onto event types with "cell" in the name instead of gone.
--
-- Site Name is resolved afterward, locally, by looking up the Site Code
-- (now resolved in Python) against the already-synced site_cache table —
-- see app/services/ape_alarm/ape_alarm_sync_service.py.
--
-- Earlier attempts at this failed with "materialized view site_lookup_mv
-- has not been populated" (that view had never been refreshed, and
-- neither the app's account nor a regular user account had permission to
-- do so) — since fixed: stg_tmp_full_access_user (the view's owner) ran
-- REFRESH MATERIALIZED VIEW site_lookup_mv, confirmed populated
-- (pg_matviews.ispopulated = true), and this query now runs successfully
-- even from a regular read account.
--
-- No date window (occurred_at IS NOT NULL only) and no event_name filter
-- means this still scans significantly more of object_138 than the
-- curated version did — bigger scan, longer exposure to
-- "conflict with recovery".
-- ==============================================================

-- name: ape_alarm
WITH ranked AS (
  SELECT
    site AS raw_site,
    additional_info,
    occurred_at,
    event_name,
    nms,
    technology,
    ROW_NUMBER() OVER (
      PARTITION BY site, event_name
      ORDER BY occurred_at DESC
    ) AS rn,
    COUNT(*) OVER (
      PARTITION BY site, event_name
    ) AS occurrence_count
  FROM object_138
  WHERE status = 'Opened'
    AND occurred_at IS NOT NULL
)
SELECT
  raw_site AS "Raw Site",
  additional_info AS "Additional Info",
  occurred_at AS "Occurred At",
  event_name AS "Event Name",
  nms AS "NMS Code",
  technology AS "Technology",
  occurrence_count AS "Occurrence Count"
FROM ranked
WHERE rn = 1
ORDER BY occurred_at DESC;
