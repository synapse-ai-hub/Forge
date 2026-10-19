-- Notifications of finished workflow runs and scheduled-task executions.
-- Exactly one of workflow_name / task_id is set (FK to the PK of each table).
-- run_id: workflow_runs.id or task_runs.id (as text) to open the detail.
-- status: success | error. read: 0 unread, 1 read.
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    workflow_name TEXT,
    task_id TEXT,
    run_id TEXT,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT,
    session_id TEXT,
    read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    CHECK (
        (workflow_name IS NOT NULL AND task_id IS NULL)
        OR (workflow_name IS NULL AND task_id IS NOT NULL)
    ),
    FOREIGN KEY (workflow_name) REFERENCES workflows(name),
    FOREIGN KEY (task_id) REFERENCES scheduled_tasks(id)
);

CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(read);
CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications(created_at);
