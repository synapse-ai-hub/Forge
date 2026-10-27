-- Cost totals (total/input/output, USD) in the time range: the messages plus the LLM calls of the
-- workflows (workflow_runs: the engine and the agent nodes, which run in memory).
-- {TIME_CLAUSE} : filter on created_at.
SELECT SUM(cost_total) AS total,
       SUM(cost_input) AS cin,
       SUM(cost_output) AS cout
FROM (
    SELECT cost_total, cost_input, cost_output, created_at FROM messages
    UNION ALL
    SELECT cost_total, cost_input, cost_output, started_at AS created_at FROM workflow_runs
    WHERE kind IN ('decision', 'judge', 'output', 'explain') OR (kind = 'node' AND node_type = 'agent')
)
WHERE cost_total IS NOT NULL {TIME_CLAUSE};
