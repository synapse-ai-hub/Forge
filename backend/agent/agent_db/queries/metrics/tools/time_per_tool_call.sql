-- Time per tool call (seconds): the execution time of each individual tool call, of the agents
-- (messages) and of the workflow nodes that run a tool (workflow_runs; run_id is the id of the
-- session of the run). NULL times are excluded so they never count as 0.
-- {TIME_CLAUSE} : filter on sessions.created_at.
SELECT t.total_time AS total_time
FROM (
    SELECT session_id, total_time FROM messages
    WHERE tool_name IS NOT NULL AND tool_name != ''
    UNION ALL
    SELECT run_id AS session_id, total_time FROM workflow_runs
    WHERE kind = 'node' AND tool_name IS NOT NULL
) t
WHERE t.total_time IS NOT NULL
AND t.session_id IN (
  SELECT session_id FROM sessions WHERE 1=1 {TIME_CLAUSE}
);
