-- Output (completion) tokens per session inside the range. One row per session.
-- {TIME_CLAUSE} : filter on sessions.created_at.
SELECT m.session_id AS sid, SUM(m.completion_tokens) AS output_tokens
FROM messages m
WHERE m.completion_tokens IS NOT NULL AND m.session_id IN (
  SELECT session_id FROM sessions WHERE 1=1 {TIME_CLAUSE}
)
GROUP BY m.session_id;
