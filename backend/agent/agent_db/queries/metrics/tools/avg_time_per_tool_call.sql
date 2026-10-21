-- Average execution time of a tool call (seconds), counting the tool calls of the agents (messages)
-- and the workflow nodes that run a tool (workflow_runs).
-- {TIME_CLAUSE} : filter on created_at.
SELECT AVG(total_time) AS avg
FROM (
    SELECT total_time, created_at FROM messages
    WHERE tool_name IS NOT NULL AND tool_name != ''
    UNION ALL
    SELECT total_time, started_at AS created_at FROM workflow_runs
    WHERE kind = 'node' AND tool_name IS NOT NULL
)
WHERE total_time IS NOT NULL {TIME_CLAUSE};
