-- Remove the node commits of every run of a deleted workflow.
DELETE FROM workflow_run_steps
WHERE run_id IN (SELECT run_id FROM workflow_runs WHERE workflow_name = ? AND kind = 'run');
