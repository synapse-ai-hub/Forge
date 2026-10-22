-- Persist a notification of a workflow run.
INSERT INTO notifications
(kind, workflow_name, run_id, title, status, message, read, created_at)
VALUES (?, ?, ?, ?, ?, ?, 0, ?);
