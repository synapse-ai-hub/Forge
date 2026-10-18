-- Mark a node as failed with its technical error.
UPDATE workflow_run_steps
SET state = 'failed', error = ?, child_session_id = COALESCE(?, child_session_id), updated_at = ?
WHERE id = ?;
