-- Token totals (total/prompt/completion) in the time range: the messages plus the LLM calls of the
-- workflows (workflow_runs: the engine and the agent nodes, which run in memory).
-- {TIME_CLAUSE} : filter on created_at.
SELECT SUM(total_tokens) AS total,
       SUM(prompt_tokens) AS prompt,
       SUM(completion_tokens) AS completion
FROM (
    SELECT total_tokens, prompt_tokens, completion_tokens, created_at FROM messages
    UNION ALL
    SELECT total_tokens, prompt_tokens, completion_tokens, started_at AS created_at FROM workflow_runs
    WHERE kind IN ('decision', 'judge', 'output', 'explain') OR (kind = 'node' AND node_type = 'agent')
)
WHERE total_tokens IS NOT NULL {TIME_CLAUSE};
