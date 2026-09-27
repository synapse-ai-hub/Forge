-- Delete all messages of a session.
DELETE FROM messages WHERE session_id = ?;
