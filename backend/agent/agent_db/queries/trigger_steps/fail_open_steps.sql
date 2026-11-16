-- Stages that were in flight when the delivery was cut: they count as failed.
UPDATE trigger_run_steps
SET state = 'failed', error = ?, updated_at = ?
WHERE event_id = ? AND state = 'open';
