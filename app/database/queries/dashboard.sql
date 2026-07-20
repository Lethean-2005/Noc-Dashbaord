-- name: summary
SELECT COUNT(*) AS total_incidents,
       SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) AS open_incidents
FROM incidents;

-- name: overview_metrics
SELECT date(created_at) AS day,
       COUNT(*) AS incident_count
FROM incidents
GROUP BY day
ORDER BY day DESC
LIMIT 30;
