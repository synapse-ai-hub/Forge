-- Number of distinct (session, turn) pairs in the time range.
-- {TIME_CLAUSE} : filter on messages.created_at.
SELECT COUNT(DISTINCT session_id || '-' || turn_number) AS cnt
FROM messages
WHERE turn_number IS NOT NULL {TIME_CLAUSE};
