-- ==============================================================
-- ALL alarm types (no event_name filter), opened, on object_138. site/
-- additional_info are selected raw, not via Postgres's
-- get_processed_site() — that ran per-row and measurably slowed the
-- query (more exposure to "conflict with recovery" on this replica).
-- app/utils/get_processed_site.py ports the same logic to Python instead,
-- using site_lookup_cache for the sran_id/nodeb_id/bts_id lookups.
--
-- Deduped: ROW_NUMBER() keeps only the latest occurrence per (site,
-- event_name, location); Occurrence Count records how many times it
-- fired. Two dedup exceptions were tried and reverted — skipping dedup
-- for "cell" events, and a category-based partial dedup — both recreated
-- the same "thousands of near-identical rows" problem dedup exists to
-- prevent; full dedup on every row is the safe default for the 9+
-- services sharing this cache.
--
-- Site Name is resolved afterward in Python, against site_cache — see
-- app/services/ape_alarm/ape_alarm_sync_service.py.
--
-- No date window and no event_name filter means this scans significantly
-- more of object_138 than a curated version would — longer exposure to
-- "conflict with recovery".
-- ==============================================================

-- name: ape_alarm
WITH ranked AS (
  SELECT
    id,
    alarm_id,
    site AS raw_site,
    additional_info,
    occurred_at,
    event_name,
    location,
    nms,
    technology,
    ROW_NUMBER() OVER (
      PARTITION BY site, event_name, location
      ORDER BY occurred_at DESC
    ) AS rn,
    COUNT(*) OVER (
      PARTITION BY site, event_name, location
    ) AS occurrence_count
  FROM object_138
  WHERE status = 'Opened'
    AND occurred_at IS NOT NULL
)
SELECT
  id AS "ID",
  alarm_id AS "Alarm ID",
  raw_site AS "Raw Site",
  additional_info AS "Additional Info",
  occurred_at AS "Occurred At",
  event_name AS "Event Name",
  location AS "Location",
  nms AS "NMS Code",
  technology AS "Technology",
  occurrence_count AS "Occurrence Count"
FROM ranked
WHERE rn = 1
ORDER BY occurred_at DESC;
