-- Total errors in the time range (provider key errors excluded).
-- {TIME_CLAUSE} : filter on error_log.created_at.
SELECT COUNT(*) AS cnt
FROM error_log
WHERE exception NOT LIKE '%key%' AND exception NOT LIKE '%api_key%' {TIME_CLAUSE};
