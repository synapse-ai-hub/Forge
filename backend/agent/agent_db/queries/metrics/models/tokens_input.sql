-- Sum of input (prompt) tokens per provider/model in the time range: the assistant and decision-model messages plus the
-- calls the workflow engine makes by itself (workflow_runs).
-- Rows with NULL or 0 tokens (failed turn, never loaded) are excluded:
-- a 0 is never a real count and would pollute averages.
-- {TIME_CLAUSE} : filter on created_at.
SELECT provider, model, SUM(prompt_tokens) AS value
FROM (
    SELECT provider, model, prompt_tokens, completion_tokens, cost_input, cost_output, cost_total, session_id, turn_number, created_at
    FROM messages
    WHERE role IN ('assistant', 'decisor')
    UNION ALL
    SELECT provider, model, prompt_tokens, completion_tokens, cost_input, cost_output, cost_total, run_id AS session_id, step AS turn_number, started_at AS created_at
    FROM workflow_runs
    WHERE kind IN ('decision', 'judge', 'output', 'explain')
)
WHERE model IS NOT NULL AND model != ''
    AND provider IS NOT NULL AND provider != ''
    AND prompt_tokens > 0 {TIME_CLAUSE}
GROUP BY provider, model
ORDER BY value DESC;
