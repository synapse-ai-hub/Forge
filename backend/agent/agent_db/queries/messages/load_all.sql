-- Load ALL messages of a session in chronological order.
SELECT * FROM messages WHERE session_id = ? ORDER BY turn_number, step, substep, id ASC;
