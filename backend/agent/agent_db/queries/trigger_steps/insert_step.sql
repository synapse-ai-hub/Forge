-- Record one dispatched stage as an open commit row.
INSERT INTO trigger_run_steps
(event_id, attempt, step, substep, node_id, node_type, args, state, created_at, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?);
