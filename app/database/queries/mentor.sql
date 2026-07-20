-- name: sessions
SELECT id, mentee, mentor, scheduled_at, status
FROM mentor_sessions
ORDER BY scheduled_at DESC;
