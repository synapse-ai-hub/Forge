-- Tool usage: call count and average execution time per tool name. It counts the tool calls of the
-- agents (messages) and the nodes of the workflows that run a tool (workflow_runs: run is shell).
-- {TIME_CLAUSE} : filter on created_at.
SELECT tool_name, COUNT(*) AS cnt, AVG(total_time) AS avg_time
FROM (
    SELECT tool_name, total_time, created_at FROM messages
    WHERE tool_name IS NOT NULL AND tool_name != ''
    UNION ALL
    SELECT tool_name, total_time, started_at AS created_at FROM workflow_runs
    WHERE kind = 'node' AND tool_name IS NOT NULL
)
WHERE 1=1 {TIME_CLAUSE}
GROUP BY tool_name
ORDER BY cnt DESC;
