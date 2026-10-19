-- Remove the notifications of a deleted workflow.
DELETE FROM notifications WHERE workflow_name = ?;
