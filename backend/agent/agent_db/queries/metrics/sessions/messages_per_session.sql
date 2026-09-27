-- Turns per session (max turn_number) inside the range. One row per session.
-- {TIME_CLAUSE} : filter on sessions.created_at.
SELECT m.session_id AS sid, MAX(m.turn_number) AS msg_count
FROM messages m
WHERE m.session_id IN (
  SELECT session_id FROM sessions WHERE 1=1 {TIME_CLAUSE}
)
GROUP BY m.session_id;
