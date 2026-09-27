-- Current max substep for a (session, turn, step); 0 when none exists
-- (the new row gets MAX+1 in Python).
SELECT COALESCE(MAX(substep), 0) FROM messages
WHERE session_id = ? AND COALESCE(turn_number, -1) = COALESCE(?, -1)
AND COALESCE(step, 0) = COALESCE(?, 0);
