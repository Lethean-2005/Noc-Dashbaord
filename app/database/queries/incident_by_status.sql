-- ==============================================================
-- Incident drilldown detail, synced into the local "incident_by_status"
-- cache table (see app/database/cache.py) every INCIDENT_SYNC_INTERVAL_SECONDS
-- — every Incident-column badge (New, New Site-Down, In-Progress,
-- In-Progress Site-Down, Overdue, Overdue Site-Down) filters from this one
-- cached table, since 'overdue' is a flag on top of status, not a separate
-- status value.
--
-- Only status IN ('new', 'in_progress') is cached — that covers every
-- Incident badge on the dashboard; resolved/closed incidents aren't shown
-- on any badge, so there's no reason to sync/store them here.
--
-- Site is matched by stripping the 2-letter province prefix off each
-- comma-separated part of site_text, then matching that against Site's
-- standard_code (its numeric code) — site_ref/site_code on Incident itself
-- are essentially never populated for alarm-raised incidents. A multi-site
-- incident (site_text has more than one entry, e.g. "SV7210,SV7032") fans
-- out to one row per site here, each carrying that incident's own status/
-- category/etc — confirmed live: taking only the first site (the old
-- behavior) silently dropped every other site of a multi-site incident
-- from every Incident-column badge and from "Incident Site Down".
--
-- "Other Site" fallback: when an incident's site isn't in the registered
-- Site list at all (e.g. a new/unlisted site), the source system's UI
-- shows an "Other Site" checkbox and lets the user type the site code
-- directly into the incident's own site_code column, with its own
-- province_ref/district/commune picked manually too — completely separate
-- from site_text. Confirmed live: INC-0000223089 has other_site=true,
-- site_code='I0229' (0 matches in object_160 — genuinely not a registered
-- site), plus its own province_ref/district/commune. Falls back to these
-- (Site Code via COALESCE; Province/District/Commune via a CASE keyed on
-- `sites.id IS NULL`, not just a blank field, since ~96 REGISTERED sites
-- also have a blank province/district/commune of their own — using
-- sites.id IS NULL instead of COALESCE on the field itself means a
-- registered-but-incomplete site's location stays correctly blank rather
-- than silently substituting the incident's own, possibly-different
-- value) so these incidents show a real Site Code/Province/District/
-- Commune instead of blank — Site Name/Hub Site/Site Grade stay blank
-- either way since there's no registered Site row to pull those from.
--
-- NMS Code is resolved locally in Python against the ne_nms_lookup_cache
-- table (site -> oldest-by-id NE's nms_name), not joined here — see
-- app/database/queries/ne_nms_lookup.sql and IncidentSyncService's
-- _normalize_status_row(). Kept out of this query specifically so the same
-- object_227 window function isn't recomputed independently across the 6
-- query files that need it.
--
-- The "latest INC-WO per (incident, site)" is NOT resolved here anymore —
-- it used to be a LATERAL subquery (ORDER BY created_at DESC LIMIT 1) that
-- ran once per outer row. object_322/object_324 are foreign tables (FDW),
-- so a per-row correlated subquery means one separate remote round-trip
-- per row — confirmed live via EXPLAIN ANALYZE: 356 rows meant 356 remote
-- calls, ~21ms each, ~7.5s of the query's ~8.5s total. IncidentSyncService
-- now does this in two cheap steps instead: this query returns the plain
-- incident/site rows (with Site Numeric ID so a row can be matched back to
-- its WOs), then ONE separate batched query
-- (app/database/queries/inc_wo_by_incident_ids.sql, scoped to just this
-- batch's incident ids) fetches every candidate WO in a single round-trip,
-- and Python picks the latest per (incident, site) itself — verified
-- against live data to produce byte-identical results to the old LATERAL
-- version, just ~100x faster on that piece.
-- ==============================================================

-- name: incident_by_status
SELECT
  inc.incident_id AS "Incident ID",
  inc.id AS "Incident Numeric ID",
  CASE inc.status
    WHEN 'in_progress' THEN 'In Progress'
    ELSE INITCAP(REPLACE(inc.status, '_', ' '))
  END AS "Incident Status",
  ploc.fra_site_name AS "Site Name",
  sites.id AS "Site Numeric ID",
  COALESCE(sites.standard_code, inc.site_code) AS "Site Code",
  inc.issue_occurred_at AS "Occurred At",
  CASE WHEN inc.overdue THEN 'Yes' ELSE 'No' END AS Overdue,
  CASE inc.incident_category
    WHEN 'bss_hardware' THEN 'BSS Hardware'
    WHEN 'bss_software' THEN 'BSS Software'
    WHEN 'oss_platform' THEN 'OSS Platform'
    WHEN 'ip_core' THEN 'IP Core'
    WHEN 'cs_core' THEN 'CS Core'
    WHEN 'ps_core' THEN 'PS Core'
    ELSE INITCAP(REPLACE(inc.incident_category, '_', ' '))
  END AS Category,
  inc.l1_noc_investigation_result AS "L1 NOC Investigation Result",
  sites.hub_site AS "Hub Site",
  INITCAP(sites.site_grade) AS "Site Grade",
  province.name AS "Province",
  district.name AS "District",
  commune.name AS "Commune"
FROM object_322 inc
LEFT JOIN LATERAL (
  SELECT DISTINCT
    TRIM(
      REGEXP_REPLACE(
        NULLIF(TRIM(site_part), ''),
        '^[A-Za-z]{2}',
        ''
      )
    ) AS site_code
  FROM UNNEST(STRING_TO_ARRAY(inc.site_text, ',')) AS site_part
) site ON TRUE
LEFT JOIN object_160 sites ON site.site_code = sites.standard_code
LEFT JOIN object_162 province
  ON (CASE WHEN sites.id IS NULL THEN inc.province_ref ELSE sites.province END) = province.id
LEFT JOIN object_164 district
  ON (CASE WHEN sites.id IS NULL THEN inc.district ELSE sites.district END) = district.id
LEFT JOIN object_166 commune
  ON (CASE WHEN sites.id IS NULL THEN inc.commune ELSE sites.commune END) = commune.id
LEFT JOIN object_308 ploc ON ploc.id = sites.physical_location
WHERE inc.status IN ('new', 'in_progress')
ORDER BY inc.issue_occurred_at DESC NULLS FIRST;
