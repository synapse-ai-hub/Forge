-- Steps per message (turn): max(step) — effort spent on each message.
-- {TIME_CLAUSE} : filter on sessions.created_at.
SELECT m.session_id AS sid, m.turn_number AS turn, MAX(m.step) AS steps
FROM messages m
WHERE m.session_id IN (
  SELECT session_id FROM sessions WHERE 1=1 {TIME_CLAUSE}
)
GROUP BY m.session_id, m.turn_number
HAVING MAX(m.step) IS NOT NULL;
