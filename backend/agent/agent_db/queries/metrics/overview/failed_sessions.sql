-- Number of distinct sessions holding at least one failed message
-- in the time range.
-- {TIME_CLAUSE} : filter on messages.created_at.
SELECT COUNT(DISTINCT session_id) AS cnt
FROM messages
WHERE status = 'error' {TIME_CLAUSE};
