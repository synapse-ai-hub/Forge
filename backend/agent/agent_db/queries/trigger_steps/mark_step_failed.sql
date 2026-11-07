-- Mark a stage as failed with its plain-language error.
UPDATE trigger_run_steps
SET state = 'failed', error = ?, updated_at = ?
WHERE id = ?;
