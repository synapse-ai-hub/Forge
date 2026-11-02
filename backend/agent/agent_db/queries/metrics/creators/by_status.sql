-- Creator requests per status (success | error | aborted) in the time range.
-- {TIME_CLAUSE} : filter on created_at.
SELECT status, COUNT(*) AS cnt
FROM creators
WHERE role = 'result' AND status IS NOT NULL AND status != '' {TIME_CLAUSE}
GROUP BY status
ORDER BY cnt DESC;
