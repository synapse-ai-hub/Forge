-- Number of messages with status 'error' in the time range (failed turns).
-- {TIME_CLAUSE} : filter on messages.created_at.
SELECT COUNT(*) AS cnt
FROM messages
WHERE status = 'error' {TIME_CLAUSE};
