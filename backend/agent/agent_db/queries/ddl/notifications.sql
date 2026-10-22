-- Notifications of finished workflow runs, whether the user played them or the scheduler started them.
-- kind: workflow (played by the user) | schedule (started by the scheduler).
-- run_id: workflow_runs.run_id of the run, to open its detail; it has no foreign key because
-- workflow_runs has many rows per run and no column is unique to reference.
-- status: success | error. read: 0 unread, 1 read. A run never opens a session: "Revisar con el agente"
-- opens a new one with the output, and the notification does not keep it.
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- internal row id
    kind TEXT NOT NULL,  -- workflow | schedule
    workflow_name TEXT NOT NULL,  -- workflow that finished
    run_id TEXT,  -- id of the run in workflow_runs (run_id)
    title TEXT NOT NULL,  -- workflow name shown in the bell
    status TEXT NOT NULL,  -- success | error
    message TEXT,  -- short text of the result or the failure explanation
    read INTEGER NOT NULL DEFAULT 0,  -- 0 unread, 1 read
    created_at TEXT NOT NULL,  -- local time, ISO format
    FOREIGN KEY (workflow_name) REFERENCES workflows(name)
);

CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(read);
CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications(created_at);
