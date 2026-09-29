-- Time per tool call (seconds): the execution time of each individual
-- tool call. NULL times are excluded so they never count as 0.
-- {TIME_CLAUSE} : filter on sessions.created_at.
SELECT m.total_time AS total_time
FROM messages m
WHERE m.tool_name IS NOT NULL AND m.tool_name != ''
AND m.total_time IS NOT NULL
AND m.session_id IN (
  SELECT session_id FROM sessions WHERE 1=1 {TIME_CLAUSE}
);