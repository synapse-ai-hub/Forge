-- Spend of an LLM call made by the workflow engine (judge or explain).
INSERT INTO workflow_usage
(workflow_name, run_id, purpose, provider, model, prompt_tokens, completion_tokens,
 total_tokens, total_time, cost_input, cost_output, cost_total, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
