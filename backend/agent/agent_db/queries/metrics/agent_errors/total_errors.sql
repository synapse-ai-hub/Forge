-- Total agent errors in the time range: messages with status 'error'
-- (failed turns and failed tool calls).
-- {TIME_CLAUSE} : filter on sessions.created_at.
SELECT COUNT(*) AS cnt
FROM messages m
WHERE m.status = 'error'
  AND m.session_id IN (
    SELECT session_id FROM sessions WHERE 1=1 {TIME_CLAUSE}
  );
