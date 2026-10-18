-- Commit the result of a node.
UPDATE workflow_run_steps
SET state = 'done', result = ?, child_session_id = COALESCE(?, child_session_id), updated_at = ?
WHERE id = ?;
