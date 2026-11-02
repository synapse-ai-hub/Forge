-- Total creator requests in the time range (one result row per request).
-- {TIME_CLAUSE} : filter on created_at.
SELECT COUNT(*) AS cnt
FROM creators
WHERE role = 'result' {TIME_CLAUSE};
