-- Commit the result of a stage.
UPDATE trigger_run_steps
SET state = 'done', result = ?, updated_at = ?
WHERE id = ?;
