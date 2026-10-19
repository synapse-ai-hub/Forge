-- Committed nodes after the step being re-run are no longer valid.
UPDATE workflow_run_steps
SET state = 'stale', updated_at = ?
WHERE run_id = ? AND state = 'done' AND step > ?;
