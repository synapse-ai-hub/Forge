-- Highest turn number of a session (NULL when the session has no messages).
SELECT MAX(turn_number) AS max_turn FROM messages WHERE session_id = ?;
