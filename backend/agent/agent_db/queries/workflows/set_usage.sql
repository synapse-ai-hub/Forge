-- Add the spend of one engine LLM call to its run (sums and the per-call detail).
UPDATE workflow_runs
SET prompt_tokens = prompt_tokens + ?, completion_tokens = completion_tokens + ?,
    total_tokens = total_tokens + ?, total_time = total_time + ?,
    cost_input = cost_input + ?, cost_output = cost_output + ?, cost_total = cost_total + ?,
    usage_calls = ?
WHERE id = ?;
