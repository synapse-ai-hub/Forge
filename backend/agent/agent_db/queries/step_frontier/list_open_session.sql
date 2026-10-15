-- All unsettled frontier rows of a session, in execution order.
SELECT * FROM step_frontier
WHERE session_id = ? AND state = 'open'
ORDER BY turn_number, step, substep ASC;
