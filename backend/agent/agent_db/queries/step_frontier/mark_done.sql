-- Flip one frontier row to done once its result commits.
UPDATE step_frontier SET state = 'done', updated_at = ?
WHERE session_id = ? AND turn_number = ? AND step = ? AND substep = ? AND state = 'open';
