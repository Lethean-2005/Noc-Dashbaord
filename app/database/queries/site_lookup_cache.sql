-- ==============================================================
-- site_lookup_mv (materialized view) on PostgreSQL — sran_id/nodeb_id/
-- bts_id -> site_name. This is the exact lookup table Postgres's own
-- get_processed_site() PL/pgSQL function queries internally (see its
-- definition) to resolve a raw NE identifier to a site name. Synced
-- locally so app/utils/get_processed_site.py can do that same lookup in Python
-- instead of Postgres calling get_processed_site() once per row of
-- object_138 — see app/database/queries/ape_alarm.sql for why that
-- per-row procedural call was worth removing.
-- ==============================================================

-- name: site_lookup_cache
SELECT sran_id, nodeb_id, bts_id, site_name
FROM site_lookup_mv;
