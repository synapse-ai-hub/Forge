-- Session creation timestamps in the range, ordered (raw input for the
-- 12-bar chart that is binned in Python).
-- {TIME_CLAUSE} : filter on sessions.created_at.
SELECT created_at AS ts
FROM sessions
WHERE 1=1 {TIME_CLAUSE}
ORDER BY created_at ASC;
