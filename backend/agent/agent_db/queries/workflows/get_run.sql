-- One run by id.
SELECT run_id AS id, workflow_name, session_id, parent_session_id, source, status, attempt, started_at, finished_at, result, error_text
FROM workflow_runs WHERE run_id = ? AND kind = 'run';
