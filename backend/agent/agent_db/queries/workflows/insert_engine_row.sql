-- Record an LLM call of the engine (decision, judge, output, explain) as the next step of its run.
INSERT INTO workflow_runs
(run_id, workflow_name, kind, attempt, step, substep, status, result, provider, model,
 prompt_tokens, completion_tokens, total_tokens, total_time, cost_input, cost_output, cost_total,
 started_at, finished_at)
SELECT r.run_id, r.workflow_name, ?, r.attempt,
       COALESCE((SELECT MAX(s.step) FROM workflow_runs s WHERE s.run_id = r.run_id), 0) + 1,
       0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
FROM workflow_runs r WHERE r.run_id = ? AND r.kind = 'run';
