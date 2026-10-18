-- Record one dispatched node as an open commit row.
INSERT INTO workflow_run_steps
(run_id, attempt, step, substep, node_id, node_type, args, state, created_at, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?);
