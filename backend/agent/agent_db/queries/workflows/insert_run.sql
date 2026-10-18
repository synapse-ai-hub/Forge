-- Open a workflow run (status running, attempt 1).
INSERT INTO workflow_runs (id, workflow_name, session_id, parent_session_id, source, status, attempt, started_at)
VALUES (?, ?, ?, ?, ?, 'running', 1, ?);
