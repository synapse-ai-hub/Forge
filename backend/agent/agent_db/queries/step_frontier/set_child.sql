-- Attach the child session id to a task frontier row once known.
UPDATE step_frontier SET child_id = ?, updated_at = ?
WHERE session_id = ? AND turn_number = ? AND step = ? AND substep = ?;
