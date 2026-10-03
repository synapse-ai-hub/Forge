-- Update the activity timestamp of a session.
UPDATE sessions SET updated_at = ? WHERE session_id = ?;
