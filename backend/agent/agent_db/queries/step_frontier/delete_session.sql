-- Delete the whole frontier of a session when the user moves on.
DELETE FROM step_frontier WHERE session_id = ?;
