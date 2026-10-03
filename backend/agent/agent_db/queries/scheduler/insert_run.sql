-- Persist a task execution result.
INSERT INTO task_runs (task_id, session_id, status, detail, started_at, finished_at)
VALUES (?, ?, ?, ?, ?, ?);
