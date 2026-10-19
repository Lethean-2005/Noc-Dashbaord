-- name: counterparty
-- object_170 ("Counterparty") — the platform's general business-partner
-- catalog (vendors, brands, site owners, energy suppliers, etc — see its
-- `type` column). This is where "Actual RAN Vendor"/"Planned RAN Vendor"
-- names like Huawei/Nokia/ZTE actually live, but it is NOT a clean 1:1
-- decode table for object_160.actual_ran_vendor — some ids conflict with
-- real-world evidence (id 21 is named "Huawei" here, but every real site
-- coded 21 is independently confirmed Nokia via live alarms — see
-- app/utils/nms.py's ACTUAL_RAN_VENDOR_TO_NMS_CODE comment). Cached
-- as-is for reference; no code currently treats this as authoritative.
SELECT
    id,
    name,
    type
FROM object_170
ORDER BY id;
