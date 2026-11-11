-- ==============================================================
-- Reference copy of the REAL PostgreSQL function this project's Site Code
-- resolution logic is ported from. Not read or executed by the app in any
-- way — object_138's site/additional_info columns are just raw text as
-- far as the app is concerned; this file exists purely so the original
-- source of truth sits next to its Python port for comparison.
--
-- Python port (what the app actually runs): app/utils/get_processed_site.py
--   - get_processed_site(site, additional_info, by_sran_id, by_nodeb_id,
--     by_bts_id) reproduces this function's exact 6-step priority chain.
--   - The sran_id/nodeb_id/bts_id -> site_name lookups this function does
--     against site_lookup_mv are done in Python instead, against the
--     site_lookup_cache table (see
--     app/services/site/site_lookup_sync_service.py), which mirrors
--     site_lookup_mv locally.
--   - Standalone demo/study script: site_code_study.py (project root).
--
-- Why the port exists: this function used to be called once per row
-- inside ape_alarm.sql's SELECT — a procedural (RBAR) call per row is
-- expensive on Postgres and made that query run measurably longer than a
-- plain column read, which increased exposure to "conflict with recovery"
-- on object_138 (a 10M-row foreign table with no supporting index). Moving
-- the computation to Python removed that per-row cost from the query
-- entirely.
-- ==============================================================

CREATE OR REPLACE FUNCTION public.get_processed_site(site_col text, additional_info_col text)
 RETURNS text
 LANGUAGE plpgsql
AS $function$

DECLARE

    processed_site TEXT;

    match_result TEXT[];

    sran_id_match TEXT;

    nodeb_id_match TEXT;

    bts_id_match TEXT;

    lookup_site_name TEXT;

BEGIN

    -- Initialize to empty strings for safety, matching Python's 'site = site or ""'

    site_col := COALESCE(site_col, '');

    additional_info_col := COALESCE(additional_info_col, '');

    processed_site := NULL;



    -----------------------------------------------------------------------

    -- Step 1: Lookup sran_id (APPLY CAST HERE)

    IF site_col LIKE 'PLMN-PLMN/MRBTS-%' THEN

        SELECT (regexp_match(site_col, 'PLMN-PLMN/MRBTS-(\d{4})(?!\d)'))[1] INTO sran_id_match;



        IF sran_id_match IS NOT NULL THEN

            SELECT site_name INTO lookup_site_name

            FROM site_lookup_mv

            -- FIX: Cast the text variable sran_id_match to BIGINT (or INT if appropriate)

            WHERE sran_id = sran_id_match::BIGINT;



            IF lookup_site_name IS NOT NULL AND LENGTH(lookup_site_name) >= 2 THEN

                RETURN SUBSTRING(lookup_site_name, 3);

            END IF;

        END IF;

    END IF;



    -----------------------------------------------------------------------

    -- Step 2: Try to extract strictly 4-digit group (and only one group) from `site`

    -- Equivalent to: digit_groups = regex.findall(r'(?<!\d)(\d{4})(?!\d)', site)

    -- This looks for groups of 4 digits, not preceded or followed by another digit.

    SELECT regexp_match(site_col, '^(?:[^0-9]|.)*?(\d{4})(?!\d)(?:[^0-9]|.)*?$') INTO match_result;



    IF ARRAY_LENGTH(match_result, 1) = 1 THEN

        RETURN match_result[1];

    END IF;



    -----------------------------------------------------------------------

    -- Step 2.5: Look for 4-digit group followed by '7MR' (e.g., DDDD7MR)

    -- Equivalent to: match = regex.search(r'(?<!\d)(\d{4})(?=7MR)', site)

    SELECT (regexp_match(site_col, '(\d{4})(?=7MR)'))[1] INTO processed_site;

    IF processed_site IS NOT NULL THEN

        RETURN processed_site;

    END IF;



    -----------------------------------------------------------------------

    -- Step 3: Lookup nodeb_id (APPLY CAST HERE)

    SELECT (regexp_match(additional_info_col, 'UIubLink=(\d{4})(?!\d)'))[1] INTO nodeb_id_match;



    IF nodeb_id_match IS NOT NULL THEN

        SELECT site_name INTO lookup_site_name

        FROM site_lookup_mv

        -- FIX: Cast the text variable nodeb_id_match to BIGINT (or INT if appropriate)

        WHERE nodeb_id = nodeb_id_match::BIGINT;



        IF lookup_site_name IS NOT NULL AND LENGTH(lookup_site_name) >= 2 THEN

            RETURN SUBSTRING(lookup_site_name, 3);

        END IF;

    END IF;



    -----------------------------------------------------------------------

    -- Step 4: Lookup bts_id (APPLY CAST HERE)

    SELECT (regexp_match(additional_info_col, 'GBtsEquipment=(\d{4})(?!\d)'))[1] INTO bts_id_match;



    IF bts_id_match IS NOT NULL THEN

        SELECT site_name INTO lookup_site_name

        FROM site_lookup_mv

        -- FIX: Cast the text variable bts_id_match to BIGINT (or INT if appropriate)

        WHERE bts_id = bts_id_match::BIGINT;



        IF lookup_site_name IS NOT NULL AND LENGTH(lookup_site_name) >= 2 THEN

            RETURN SUBSTRING(lookup_site_name, 3);

        END IF;

    END IF;



    -----------------------------------------------------------------------

    -- Step 5 (Original Step 4 in Python): Look for XXXXXXDDDDXXX pattern

    -- Equivalent to: regex.search(r'[A-Za-z]{6}(\d{4})[A-Za-z]{3}', additional_info)

    SELECT (regexp_match(additional_info_col, '[A-Za-z]{6}(\d{4})[A-Za-z]{3}'))[1] INTO processed_site;



    IF processed_site IS NOT NULL THEN

        RETURN processed_site;

    END IF;



    -----------------------------------------------------------------------

    -- Final return (Equivalent to: return None)

    RETURN NULL;

END;

$function$
