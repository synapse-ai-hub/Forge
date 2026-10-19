-- Remove the runs of a deleted workflow.
DELETE FROM workflow_runs WHERE workflow_name = ?;
