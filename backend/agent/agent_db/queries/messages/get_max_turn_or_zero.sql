-- Highest turn number of a session, 0 when the session has no messages.
SELECT COALESCE(MAX(turn_number), 0) AS max_turn
FROM messages WHERE session_id = ?;
