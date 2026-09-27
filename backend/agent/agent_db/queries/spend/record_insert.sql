-- Create the current month's spend row when it does not exist yet.
INSERT INTO spend
(provider, model, month, requests, prompt_tokens, completion_tokens, total_tokens,
 cost_input, cost_output, cost_total, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
