-- Persist a single message row.
INSERT INTO messages
(session_id, role, content, reasoning, tool_calls, tool_results,
status, message, prompt_tokens, completion_tokens, total_tokens, total_time,
time_to_first_token,
tool_call_id, tool_name, model, provider, cost_input, cost_output, cost_total,
turn_number, step, substep, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
