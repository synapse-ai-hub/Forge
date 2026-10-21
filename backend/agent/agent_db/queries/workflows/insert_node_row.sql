-- Record one execution of a node in its run (kind node), with its spend.
INSERT INTO workflow_runs
(run_id, workflow_name, kind, attempt, step, substep, node_id, node_type, tool_name, status, child_session_id,
 result, error_text, provider, model, prompt_tokens, completion_tokens, total_tokens, total_time,
 cost_input, cost_output, cost_total, started_at, finished_at)
SELECT r.run_id, r.workflow_name, 'node', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
FROM workflow_runs r WHERE r.run_id = ? AND r.kind = 'run';
