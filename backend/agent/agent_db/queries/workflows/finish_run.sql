-- Close a run with its final status, answer and plain-language error.
UPDATE workflow_runs
SET status = ?, finished_at = ?, result = ?, error_text = ?
WHERE id = ?;
