-- Agent errors per turn: count of messages with status 'error'
-- in each (session, turn).
-- {TIME_CLAUSE} : filter on sessions.created_at.
-- {MODEL_CLAUSE} : optional filter on m.model / m.provider.
SELECT m.session_id AS sid, m.turn_number AS turn, COUNT(*) AS value
FROM messages m
WHERE m.status = 'error'
  AND m.session_id IN (
    SELECT session_id FROM sessions WHERE 1=1 {TIME_CLAUSE}
  )
  {MODEL_CLAUSE}
GROUP BY m.session_id, m.turn_number
