-- Agent errors per tool call: failed tool executions
-- (role 'tool' with status 'error'). Only rows with a recorded tool_name
-- are counted.
-- {TIME_CLAUSE} : filter on sessions.created_at.
SELECT m.tool_name AS tool, COUNT(*) AS cnt
FROM messages m
WHERE m.role = 'tool'
  AND m.status = 'error'
  AND m.tool_name IS NOT NULL
  AND m.session_id IN (
    SELECT session_id FROM sessions WHERE 1=1 {TIME_CLAUSE}
  )
GROUP BY m.tool_name
ORDER BY cnt DESC;
