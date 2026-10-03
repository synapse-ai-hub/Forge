-- Full sessions table in the time range (CSV export).
-- {TIME_CLAUSE} : filter on sessions.created_at.
SELECT *
FROM sessions
WHERE 1=1 {TIME_CLAUSE}
ORDER BY created_at ASC;
