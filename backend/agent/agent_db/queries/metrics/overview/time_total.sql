-- Total execution/LLM time (seconds) in the time range: the messages plus every row of the workflows
-- but the run itself (workflow_runs: the LLM calls of the engine, the agent nodes, the nodes that run
-- a tool and the tools an agent node called).
-- {TIME_CLAUSE} : filter on created_at.
SELECT SUM(total_time) AS total
FROM (
    SELECT total_time, created_at FROM messages
    UNION ALL
    SELECT total_time, started_at AS created_at FROM workflow_runs
    WHERE kind != 'run'
)
WHERE total_time IS NOT NULL {TIME_CLAUSE};
