-- Remove the registry row of a deleted workflow.
DELETE FROM workflows WHERE name = ?;
