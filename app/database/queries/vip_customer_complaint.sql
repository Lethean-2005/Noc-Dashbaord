-- ==============================================================
-- VIP Customer Complaint — synced into the local "vip_customer_complaint"
-- cache table (see app/database/cache.py) every
-- INCIDENT_SYNC_INTERVAL_SECONDS. Every new, not-yet-worked customer
-- complaint raised by a VIP customer.
-- ==============================================================

-- name: vip_customer_complaint
SELECT
  incident_id AS "Incident ID",
  customer_address AS "Customer Address",
  customer_phone_no AS "Customer Phone No",
  complaint_raised_at AS "Problem Experienced At",
  fault_description AS "Fault Description"
FROM object_322
WHERE status = 'new'
  AND incident_category = 'customer_complaint'
  AND vip_customer = TRUE
ORDER BY complaint_raised_at DESC NULLS LAST;
