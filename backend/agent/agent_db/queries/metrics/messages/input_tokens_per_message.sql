-- Input tokens per message (turn): size of the prompt. SUM skips NULL
-- rows; turns with no loaded token count are excluded (never a fake 0).
-- {TIME_CLAUSE} : filter on sessions.created_at.
SELECT m.session_id AS sid, m.turn_number AS turn, SUM(m.prompt_tokens) AS input_tokens
FROM messages m
WHERE m.session_id IN (
  SELECT session_id FROM sessions WHERE 1=1 {TIME_CLAUSE}
)
GROUP BY m.session_id, m.turn_number
HAVING SUM(m.prompt_tokens) IS NOT NULL;
