-- Runs still marked as running (active now, or cut by a backend crash).
SELECT run_id AS id, workflow_name, parent_session_id, source, status, attempt, started_at, finished_at, result, error_text
FROM workflow_runs WHERE kind = 'run' AND status = 'running' ORDER BY started_at ASC;
