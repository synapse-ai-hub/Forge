-- Open a workflow run (status running, attempt 1).
INSERT INTO workflow_runs (run_id, workflow_name, kind, parent_session_id, source, status, attempt, started_at)
VALUES (?, ?, 'run', ?, ?, 'running', 1, ?);
