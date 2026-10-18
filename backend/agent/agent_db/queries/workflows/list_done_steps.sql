-- Committed nodes of a run, in execution order.
SELECT * FROM workflow_run_steps
WHERE run_id = ? AND state = 'done'
ORDER BY step, substep, id;
