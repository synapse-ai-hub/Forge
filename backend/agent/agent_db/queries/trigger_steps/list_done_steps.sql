-- Committed stages of a delivery, in execution order.
SELECT * FROM trigger_run_steps
WHERE event_id = ? AND state = 'done'
ORDER BY step, substep, id;
