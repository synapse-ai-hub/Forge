-- Nodes that were in flight when the run was cut: they count as failed.
UPDATE workflow_run_steps
SET state = 'failed', error = ?, updated_at = ?
WHERE run_id = ? AND state = 'open';
