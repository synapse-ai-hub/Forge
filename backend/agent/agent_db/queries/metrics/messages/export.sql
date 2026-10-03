-- Full messages table in the time range (CSV export).
-- {TIME_CLAUSE} : filter on messages.created_at.
SELECT *
FROM messages
WHERE 1=1 {TIME_CLAUSE}
ORDER BY created_at ASC;
