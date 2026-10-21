-- Notifications of finished workflow runs and scheduled-task executions.
-- Exactly one of workflow_name / task_id is set (FK to the PK of each table).
-- run_id: workflow_runs.run_id or task_runs.id (as text) to open the detail; it has no foreign
-- key because it points to one table or the other depending on kind.
-- status: success | error. read: 0 unread, 1 read.
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- internal row id
    kind TEXT NOT NULL,  -- workflow | task
    workflow_name TEXT,  -- workflow that finished (kind workflow)
    task_id TEXT,  -- scheduled task that finished (kind task)
    run_id TEXT,  -- id of the run in workflow_runs (run_id) or task_runs (id)
    title TEXT NOT NULL,  -- workflow or task name shown in the bell
    status TEXT NOT NULL,  -- success | error
    message TEXT,  -- short text of the result or the failure explanation
    session_id TEXT,  -- session of the execution, while it exists
    read INTEGER NOT NULL DEFAULT 0,  -- 0 unread, 1 read
    created_at TEXT NOT NULL,  -- local time, ISO format
    CHECK (
        (workflow_name IS NOT NULL AND task_id IS NULL)
        OR (workflow_name IS NULL AND task_id IS NOT NULL)
    ),
    FOREIGN KEY (workflow_name) REFERENCES workflows(name),
    FOREIGN KEY (task_id) REFERENCES scheduled_tasks(id),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(read);
CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications(created_at);
