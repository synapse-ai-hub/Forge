-- Every node execution of a run, in order.
SELECT * FROM workflow_run_steps WHERE run_id = ? ORDER BY id ASC;
