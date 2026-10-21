-- Failed tool calls grouped by tool name: the ones of the agents (messages) and the workflow nodes
-- that run a tool (workflow_runs; run_id is the id of the session of the run).
-- {TIME_CLAUSE} : filter on sessions.created_at.
SELECT m.tool AS tool, COUNT(*) AS cnt
FROM (
    SELECT session_id, tool_name AS tool FROM messages
    WHERE role = 'tool' AND status = 'error' AND tool_name IS NOT NULL
    UNION ALL
    SELECT run_id AS session_id, tool_name AS tool FROM workflow_runs
    WHERE kind = 'node' AND tool_name IS NOT NULL AND status = 'error'
) m
WHERE m.session_id IN (
    SELECT session_id FROM sessions WHERE 1=1 {TIME_CLAUSE}
)
GROUP BY m.tool
ORDER BY cnt DESC;
