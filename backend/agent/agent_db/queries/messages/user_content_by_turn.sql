-- User message content of a given turn (resume context source).
SELECT content FROM messages
WHERE session_id = ? AND role = 'user' AND turn_number = ?
ORDER BY id ASC LIMIT 1;
