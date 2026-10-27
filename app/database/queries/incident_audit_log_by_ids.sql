-- ==============================================================
-- Every field-change audit entry (object_323, "Audit for model #322")
-- for a batch of incidents — the OTHER half of Streamline's own
-- "Worklog" tab, alongside incident_worklog_by_ids.sql's free-text
-- comments. Streamline's UI merges both into one timeline (confirmed
-- live against a real incident: 4 rows from object_362 + 3 rows from
-- object_323 = the 7 entries shown on screen); this app follows the
-- same split-then-merge shape at the Python layer rather than a SQL
-- UNION, since the two sources have very different column shapes.
--
-- Generic, metadata-driven value resolution — NOT hardcoded per field,
-- so any field added to the Incident model later resolves correctly
-- with zero changes here:
--   - object_2 (field) describes EVERY field on Incident, keyed by
--     related_field. Its own "options" JSON carries everything needed:
--       * array_string (choice) fields: options->'values' is the raw
--         code -> display label map (e.g. "new" -> "New") — looked up
--         directly via jsonb ->>, no CASE/enum table needed.
--       * reference fields: options->>'foreign_model' names which
--         OTHER model the raw id in "from"/"to" points at (e.g.
--         "user", "team") — resolved below via object_1 (model
--         catalog)'s own alias -> real object_<id> table mapping,
--         confirmed live: user=object_3, team=object_310,
--         provinces=object_162, rca_category=object_356 (the only 4
--         foreign_models that actually appear on Incident's own audit
--         log today — grepped live via "SELECT DISTINCT related_field
--         ... JOIN object_2" against object_323).
--   - "from"/"to" are plain TEXT columns holding either a raw choice
--     code, a raw numeric id-as-string, or already-human-readable text
--     (string/datetime/boolean fields) depending on the field's type —
--     the CASE chain below picks the right interpretation per row.
--
-- Safety: every id lookup casts "from"/"to" to integer INSIDE a CASE
-- WHEN (not a bare ::integer gated only by an AND alongside a regex
-- check) — confirmed live that Postgres does NOT reliably short-
-- circuit AND in a JOIN's ON clause (a bare cast there threw
-- "invalid input syntax for type integer: new" on a Status row even
-- though its foreign_model check should have excluded it). A CASE
-- WHEN's branches ARE guaranteed sequential per the SQL standard, so
-- the cast only ever runs once its own regex guard already passed.
-- NULLIF(...,'') on every resolved reference value turns Postgres's
-- CONCAT-of-two-NULLs empty string ('') back into a real NULL, so an
-- unset reference displays the same blank way a never-set choice/
-- string field already does.
-- ==============================================================

-- name: incident_audit_log_by_ids
SELECT
  inc.id AS "Incident Numeric ID",
  inc.incident_id AS "Incident ID",
  f.name AS "Field",
  CASE
    WHEN f.type = 'array_string' THEN COALESCE((f.options::jsonb -> 'values' ->> a."from"), a."from")
    WHEN f.options::jsonb ->> 'foreign_model' = 'user' THEN NULLIF(TRIM(CONCAT(fu.name, ' ', fu.surname)), '')
    WHEN f.options::jsonb ->> 'foreign_model' = 'team' THEN ft.name
    WHEN f.options::jsonb ->> 'foreign_model' = 'provinces' THEN fp.name
    WHEN f.options::jsonb ->> 'foreign_model' = 'rca_category' THEN fr.root_cause_category_name
    ELSE a."from"
  END AS "From",
  CASE
    WHEN f.type = 'array_string' THEN COALESCE((f.options::jsonb -> 'values' ->> a."to"), a."to")
    WHEN f.options::jsonb ->> 'foreign_model' = 'user' THEN NULLIF(TRIM(CONCAT(tu.name, ' ', tu.surname)), '')
    WHEN f.options::jsonb ->> 'foreign_model' = 'team' THEN tt.name
    WHEN f.options::jsonb ->> 'foreign_model' = 'provinces' THEN tp.name
    WHEN f.options::jsonb ->> 'foreign_model' = 'rca_category' THEN tr.root_cause_category_name
    ELSE a."to"
  END AS "To",
  a.created_at AS "Created At",
  TRIM(CONCAT(u.name, ' ', u.surname)) AS "Created By"
FROM object_323 a
JOIN object_322 inc ON inc.id = a.related_record
LEFT JOIN object_2 f ON f.id = a.related_field
LEFT JOIN object_3 u ON u.id = a.created_by
LEFT JOIN object_3 fu ON fu.id = (CASE WHEN f.options::jsonb ->> 'foreign_model' = 'user' AND a."from" ~ '^[0-9]+$' THEN a."from"::integer END)
LEFT JOIN object_3 tu ON tu.id = (CASE WHEN f.options::jsonb ->> 'foreign_model' = 'user' AND a."to" ~ '^[0-9]+$' THEN a."to"::integer END)
LEFT JOIN object_310 ft ON ft.id = (CASE WHEN f.options::jsonb ->> 'foreign_model' = 'team' AND a."from" ~ '^[0-9]+$' THEN a."from"::integer END)
LEFT JOIN object_310 tt ON tt.id = (CASE WHEN f.options::jsonb ->> 'foreign_model' = 'team' AND a."to" ~ '^[0-9]+$' THEN a."to"::integer END)
LEFT JOIN object_162 fp ON fp.id = (CASE WHEN f.options::jsonb ->> 'foreign_model' = 'provinces' AND a."from" ~ '^[0-9]+$' THEN a."from"::integer END)
LEFT JOIN object_162 tp ON tp.id = (CASE WHEN f.options::jsonb ->> 'foreign_model' = 'provinces' AND a."to" ~ '^[0-9]+$' THEN a."to"::integer END)
LEFT JOIN object_356 fr ON fr.id = (CASE WHEN f.options::jsonb ->> 'foreign_model' = 'rca_category' AND a."from" ~ '^[0-9]+$' THEN a."from"::integer END)
LEFT JOIN object_356 tr ON tr.id = (CASE WHEN f.options::jsonb ->> 'foreign_model' = 'rca_category' AND a."to" ~ '^[0-9]+$' THEN a."to"::integer END)
WHERE a.related_record = ANY(:incident_ids)
ORDER BY a.created_at DESC;
