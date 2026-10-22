-- LLM calls per provider/model in the time range: the assistant and decision-model messages plus the LLM calls of the
-- workflows (workflow_runs: the engine and the agent nodes; an agent node counts once).
-- {TIME_CLAUSE} : filter on created_at.
SELECT provider, model, COUNT(*) AS cnt
FROM (
    SELECT provider, model, prompt_tokens, completion_tokens, cost_input, cost_output, cost_total, session_id, turn_number, created_at
    FROM messages
    WHERE role IN ('assistant', 'decisor')
    UNION ALL
    SELECT provider, model, prompt_tokens, completion_tokens, cost_input, cost_output, cost_total, run_id AS session_id, step AS turn_number, started_at AS created_at
    FROM workflow_runs
    WHERE kind IN ('decision', 'judge', 'output', 'explain') OR (kind = 'node' AND node_type = 'agent')
)
WHERE model IS NOT NULL AND model != ''
    AND provider IS NOT NULL AND provider != '' {TIME_CLAUSE}
GROUP BY provider, model
ORDER BY cnt DESC;
