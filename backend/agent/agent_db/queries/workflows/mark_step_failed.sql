-- Mark a node as failed with its technical error.
UPDATE workflow_run_steps
SET state = 'failed', error = ?, updated_at = ?
WHERE id = ?;
