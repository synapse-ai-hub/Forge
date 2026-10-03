-- Record a direct LLM call made outside the chat loop.
INSERT INTO creator_calls
(caller, provider, model, prompt_tokens, completion_tokens,
 total_tokens, total_time, cost_input, cost_output,
 cost_total, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
