-- ==============================================================
-- Site Down 24h Teams alert's Stage 2 (restore-confirmation) — given a
-- batch of incident_id strings already down-alerted and still pending
-- restore-confirmation (site_down_24h_alert_cache's own
-- pending_restore_incident_ids()), returns just the ones that have
-- actually resolved by now, with what Stage 2's own message needs:
-- the restored timestamp and the (already-available, see
-- incident_site_down.sql's own header) L1 NOC Investigation Result as
-- Root Cause — same field Stage 1 used, confirmed by the user's own
-- real examples to carry the SAME value across both posts, not a
-- different "actual root cause" set later at formal resolution.
--
-- "Restored At" splits by Source, confirmed by the user: an
-- Alarms-sourced incident's real restore signal is the alarm actually
-- clearing (cleared_alarm_received_at), NOT the ticket being closed —
-- NOC can leave a ticket open well after the site is physically back.
-- A non-Alarms incident (NOC/Field/Customer Complaint) has no alarm
-- feed behind it at all, so resolved_at (the ticket's own resolution)
-- is the only real signal available. Same source-based split as
-- incident_site_down.sql's own "Occurred At" column, for the matching
-- down-side timestamp.
--
-- Scoped to a specific batch of ids, same "safe to join here" reasoning
-- as incident_closed_trend_by_ids.sql — this only ever touches the
-- small number of rows still pending a restore-confirmation, not a
-- full-table scan.
-- ==============================================================

-- name: incident_site_down_restored_by_ids
SELECT
  inc.incident_id AS "Incident ID",
  CASE
    WHEN LOWER(inc.source) = 'alarms' THEN inc.cleared_alarm_received_at
    ELSE inc.resolved_at
  END AS "Restored At",
  inc.l1_noc_investigation_result AS "L1 NOC Investigation Result",
  inc.last_comments AS "Last Comments"
FROM object_322 inc
WHERE inc.incident_id = ANY(:incident_ids)
  AND (
    (LOWER(inc.source) = 'alarms' AND inc.cleared_alarm_received_at IS NOT NULL)
    OR (LOWER(inc.source) != 'alarms' AND inc.resolved_at IS NOT NULL)
  );
