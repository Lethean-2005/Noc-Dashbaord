-- name: incident_site_down_restored_by_ids
-- Restoration is determined by the source-specific timestamp, not a status filter.
-- Alarms: Issue Occurred At -> Cleared Alarm Received At.
-- NOC/manual: Created At -> Closed At; wait if Closed At is still blank.
-- Source UTC values are converted exactly once to Cambodia time in Python.
SELECT
  inc.incident_id AS "Incident ID",
  CASE WHEN LOWER(TRIM(inc.source)) = 'alarms'
       THEN inc.issue_occurred_at ELSE inc.created_at END AS "Occurred At",
  CASE WHEN LOWER(TRIM(inc.source)) = 'alarms'
       THEN inc.cleared_alarm_received_at ELSE inc.closed_at END AS "Restored At",
  inc.actual_root_cause AS "Actual Root Cause",
  inc.resolution AS "Resolution"
FROM object_322 inc
WHERE inc.incident_id = ANY(:incident_ids)
  AND NULLIF(TRIM(inc.source), '') IS NOT NULL
  AND (
    (LOWER(TRIM(inc.source)) = 'alarms'
      AND inc.cleared_alarm_received_at IS NOT NULL
      AND inc.issue_occurred_at IS NOT NULL
      AND inc.cleared_alarm_received_at >= inc.issue_occurred_at)
    OR
    (LOWER(TRIM(inc.source)) != 'alarms'
      AND inc.created_at IS NOT NULL
      AND inc.closed_at IS NOT NULL
      AND inc.closed_at >= inc.created_at)
  );
