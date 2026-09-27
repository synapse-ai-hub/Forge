-- Errors per day in the time range (provider key errors excluded).
-- {TIME_CLAUSE} : filter on error_log.created_at.
SELECT date(created_at) AS day, COUNT(*) AS cnt
FROM error_log
WHERE 1=1 {TIME_CLAUSE}
    AND exception NOT LIKE '%key%'
    AND exception NOT LIKE '%api_key%'
GROUP BY date(created_at)
ORDER BY day ASC;
