-- name: list
SELECT id, title, status, created_at
FROM reports
ORDER BY created_at DESC
LIMIT :limit OFFSET :offset;
