-- Time per message (turn): SUM of assistant + tool total_time — the cost
-- of each response. Rows with a NULL time are not counted; turns whose
-- times were never loaded are excluded (NULL never becomes 0).
-- {TIME_CLAUSE} : filter on sessions.created_at.
SELECT m.session_id AS sid, m.turn_number AS turn, SUM(m.total_time) AS total_time
FROM messages m
WHERE m.session_id IN (
  SELECT session_id FROM sessions WHERE 1=1 {TIME_CLAUSE}
)
AND (m.role = 'assistant' OR m.role = 'tool')
GROUP BY m.session_id, m.turn_number
HAVING SUM(m.total_time) IS NOT NULL;

select * from messages 
where session_id = '452f2dbf-79f0-4351-bb9c-a21712691adf' and turn_number = 4;
