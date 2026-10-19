-- Add the usage of one LLM call to the run that made it.
UPDATE creator_runs
SET llm_calls = llm_calls + 1,
    prompt_tokens = prompt_tokens + ?,
    completion_tokens = completion_tokens + ?,
    total_tokens = total_tokens + ?,
    cost_input = cost_input + ?,
    cost_output = cost_output + ?,
    cost_total = cost_total + ?
WHERE id = ?;
