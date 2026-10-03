-- Sessions created per day in the time range.
-- {TIME_CLAUSE} : filter on sessions.created_at.
SELECT date(created_at) AS day, COUNT(*) AS cnt
FROM sessions
WHERE 1=1 {TIME_CLAUSE}
GROUP BY date(created_at)
ORDER BY day ASC;
