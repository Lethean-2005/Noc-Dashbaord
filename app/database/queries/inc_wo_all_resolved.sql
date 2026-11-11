-- name: inc_wo_all_resolved
-- Use the Incident source flag AND verify siblings; stale flags cannot hide open WOs.
-- One row per non-closed incident with at least one WO and EVERY linked
-- WO strictly resolved. Do not filter WO statuses before aggregation:
-- open, reopened, closed and NULL-status siblings must all block the badge.
-- No site joins: those can multiply WO rows on multi-site incidents.
SELECT inc.incident_id,
       inc.id AS incident_numeric_id,
       inc.all_wo_is_resolved,
       CASE inc.status WHEN 'in_progress' THEN 'In Progress'
            ELSE INITCAP(REPLACE(inc.status, '_', ' ')) END AS incident_status,
       INITCAP(REPLACE(inc.incident_category, '_', ' ')) AS incident_category,
       inc.site_code,
       inc.site_text,
       inc.issue_occurred_at AS occurred_at,
       COUNT(*) AS wo_count,
       COUNT(*) FILTER (WHERE wo.status = 'resolved') AS resolved_wo_count,
       MAX(wo.resolved_at) AS resolved_at
FROM object_322 inc
JOIN object_324 wo ON wo.parent_incident = inc.id
WHERE inc.status != 'closed' AND inc.all_wo_is_resolved IS TRUE
AND (inc.incident_category IS DISTINCT FROM 'customer_complaint' OR inc.status = 'in_progress')
GROUP BY inc.id, inc.incident_id, inc.all_wo_is_resolved, inc.status, inc.incident_category,
         inc.site_code,
       inc.site_text, inc.issue_occurred_at
HAVING COUNT(*) > 0
   AND COUNT(*) = COUNT(*) FILTER (WHERE wo.status = 'resolved')
ORDER BY MAX(wo.resolved_at) DESC NULLS LAST, inc.id;
