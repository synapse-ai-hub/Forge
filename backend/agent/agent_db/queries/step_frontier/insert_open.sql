-- Record one dispatched block call as an open frontier row.
INSERT INTO step_frontier
(session_id, turn_number, step, substep, tool_call_id, tool_name, tool_args, state, child_id, created_at, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?);
