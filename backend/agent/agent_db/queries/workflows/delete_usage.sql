-- Remove the engine spend rows of a deleted workflow.
DELETE FROM workflow_usage WHERE workflow_name = ?;
