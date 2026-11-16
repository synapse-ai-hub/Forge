-- Committed stages after the stage being re-run are no longer valid.
UPDATE trigger_run_steps
SET state = 'stale', updated_at = ?
WHERE event_id = ? AND state = 'done' AND step > ?;
