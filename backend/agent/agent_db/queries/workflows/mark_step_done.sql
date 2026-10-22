-- Commit the result of a node.
UPDATE workflow_run_steps
SET state = 'done', result = ?, updated_at = ?
WHERE id = ?;
