-- Every site whose actual_ran_vendor code is still unconfirmed — see
-- app/utils/nms.py's ACTUAL_RAN_VENDOR_TO_NMS_CODE for the current,
-- confirmed set (6=ZTE, 7=Nokia, 20=Huawei — each an exact on-air
-- site-count match against Streamline's own "Actual RAN Vendor" filter,
-- confirmed 2026-08-27). Everything else, including 21/22 (both
-- Counterparty records also named "Huawei", but not counted under that
-- filter — see nms.py's comment), stays unconfirmed until checked the
-- same way: an exact count match, not just a matching display name.
--
-- Before assuming what an unconfirmed code means, check its name/type in
-- the local counterparty_cache (synced from Streamline's own
-- counterparties_catalog, object_170):
--
--   SELECT id, name, type FROM counterparty_cache WHERE id IN (5, 58, 115, ...);
--
-- (58 = "Other" — not a real vendor. 115 = "Alcatel" — a real, distinct
-- vendor, different from ZTE/Nokia/Huawei.)
SELECT
    standard_code,
    name,
    status,
    actual_ran_vendor
FROM object_160
WHERE actual_ran_vendor NOT IN (6, 7, 20)
  AND actual_ran_vendor IS NOT NULL
ORDER BY actual_ran_vendor, name;
