-- name: site_ran_vendor
-- object_160.actual_ran_vendor — a site-level "who actually runs this
-- site's RAN today" field, separate from object_227's per-NE inventory
-- (which the "lowest NE id wins" tie-break in ne_nms_lookup.sql can leave
-- stale after an equipment/vendor swap). Only rows with a value are
-- selected — most sites have none set.
SELECT
  sites.standard_code AS "Site Code",
  sites.actual_ran_vendor AS "Actual RAN Vendor"
FROM object_160 sites
WHERE sites.actual_ran_vendor IS NOT NULL;
