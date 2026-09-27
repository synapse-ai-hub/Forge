-- Delete a session row (messages are deleted separately).
DELETE FROM sessions WHERE session_id = ?;
