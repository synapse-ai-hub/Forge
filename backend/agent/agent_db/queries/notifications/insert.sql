-- Persist a notification (workflow run or scheduled task).
INSERT INTO notifications
(kind, workflow_name, task_id, run_id, title, status, message, session_id, read, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?);
