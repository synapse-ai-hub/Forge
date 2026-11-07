-- Close a delivery with its final status, answer and plain-language error.
UPDATE trigger_runs
SET status = ?, finished_at = ?, result = ?, error_text = ?, workflow_run_id = ?
WHERE event_id = ?;
