-- Load messages from a given turn onwards (min_turn inclusive),
-- in chronological order.
SELECT * FROM messages WHERE session_id = ? AND turn_number >= ?
ORDER BY turn_number, step, substep, id ASC;
