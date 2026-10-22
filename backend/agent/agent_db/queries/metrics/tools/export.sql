-- Tool calls in the time range (CSV export): the ones of the agents (messages) and, in the workflows
-- (workflow_runs), the nodes that run a tool and the tools an agent node called (the run id goes in
-- session_id and the step in turn_number).
-- {TIME_CLAUSE} : filter on created_at.
SELECT session_id, turn_number, tool_name, total_time, created_at
FROM (
    SELECT session_id, turn_number, tool_name, total_time, created_at FROM messages
    WHERE tool_name IS NOT NULL AND tool_name != ''
    UNION ALL
    SELECT run_id AS session_id, step AS turn_number, tool_name, total_time, started_at AS created_at
    FROM workflow_runs
    WHERE kind IN ('node', 'tool') AND tool_name IS NOT NULL
)
WHERE 1=1 {TIME_CLAUSE}
ORDER BY created_at ASC;
