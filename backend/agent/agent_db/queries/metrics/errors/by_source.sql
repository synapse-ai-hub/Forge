-- Top 10 error sources in the time range (missing API keys are not
-- agent errors, so provider_key sources are excluded).
-- {TIME_CLAUSE} : filter on error_log.created_at.
SELECT source, COUNT(*) AS cnt
FROM error_log
WHERE source IS NOT NULL AND source != ''
    AND source NOT LIKE '%provider_keys%'
    AND exception NOT LIKE '%key%'
    AND exception NOT LIKE '%api_key%' {TIME_CLAUSE}
GROUP BY source
ORDER BY cnt DESC
LIMIT 10;
