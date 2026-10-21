-- Total execution/LLM time (seconds) in the time range: the messages plus the LLM calls of the workflow
-- engine and the workflow nodes that run a tool (workflow_runs; the agent nodes are already in
-- their messages).
-- {TIME_CLAUSE} : filter on created_at.
SELECT SUM(total_time) AS total
FROM (
    SELECT total_time, created_at FROM messages
    UNION ALL
    SELECT total_time, started_at AS created_at FROM workflow_runs
    WHERE kind IN ('decision', 'judge', 'output', 'explain') OR (kind = 'node' AND tool_name IS NOT NULL)
)
WHERE total_time IS NOT NULL {TIME_CLAUSE};
