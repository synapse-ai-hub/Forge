-- Total messages in the time range.
-- {TIME_CLAUSE} : filter on messages.created_at.
SELECT COUNT(*) AS cnt
FROM messages
WHERE 1=1 {TIME_CLAUSE};
