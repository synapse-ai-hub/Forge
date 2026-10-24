-- Insert a row of a creator conversation or one of its LLM calls.
INSERT INTO creators
(creator_id, kind, role, content, reasoning, tool_calls, tool_results, tool_name, status, message,
 caller, action, item_name, setup, provider, model, prompt_tokens, completion_tokens, total_tokens,
 total_time, time_to_first_token, cost_input, cost_output, cost_total, turn_number, step, substep, tool_call_id, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
