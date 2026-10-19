-- Attach the parent session to a run.
UPDATE workflow_runs SET session_id = ? WHERE id = ?;
