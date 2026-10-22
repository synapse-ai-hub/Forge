-- Record one tool call of an agent node in its run (kind tool), at the step and substep of the node.
INSERT INTO workflow_runs
(run_id, workflow_name, kind, attempt, step, substep, node_id, node_type, tool_name, status,
 result, error_text, total_time, started_at, finished_at)
SELECT r.run_id, r.workflow_name, 'tool', ?, ?, ?, ?, 'agent', ?, ?, ?, ?, ?, ?, ?
FROM workflow_runs r WHERE r.run_id = ? AND r.kind = 'run';
