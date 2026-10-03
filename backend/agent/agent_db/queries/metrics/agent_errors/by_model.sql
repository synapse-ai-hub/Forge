-- Agent errors per provider/model: messages with status 'error'
-- (failed turns and failed tool calls). Only rows with a recorded model
-- are counted; error_log (backend/programming errors) is never used here.
-- {TIME_CLAUSE} : filter on sessions.created_at.
SELECT m.provider AS provider, m.model AS model, COUNT(*) AS cnt
FROM messages m
WHERE m.status = 'error'
  AND m.provider IS NOT NULL
  AND m.model IS NOT NULL
  AND m.session_id IN (
    SELECT session_id FROM sessions WHERE 1=1 {TIME_CLAUSE}
  )
GROUP BY m.provider, m.model
ORDER BY cnt DESC;
