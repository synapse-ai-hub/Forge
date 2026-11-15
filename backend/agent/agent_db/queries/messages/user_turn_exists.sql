-- Whether a user message already exists for a turn (1 when present, no row otherwise).
SELECT 1 FROM messages WHERE session_id = ? AND turn_number = ? AND role = 'user' LIMIT 1;
