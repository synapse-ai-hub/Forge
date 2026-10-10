-- Delete the whole frontier of a turn when its step closes validated.
DELETE FROM step_frontier WHERE session_id = ? AND turn_number = ?;
