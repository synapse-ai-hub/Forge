-- Total sessions in the time range.
-- {TIME_CLAUSE} : filter on sessions.created_at.
SELECT COUNT(*) AS cnt
FROM sessions
WHERE 1=1 {TIME_CLAUSE};
