-- One row per execution of a scheduled task. The session of the run is kept as long as it
-- exists; if it is deleted the run stays without session.
CREATE TABLE IF NOT EXISTS task_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- internal row id; also the run_id of its notification
    task_id TEXT NOT NULL,  -- task that ran
    session_id TEXT,  -- session where the agent worked
    status TEXT NOT NULL,  -- success | error
    detail TEXT,  -- first characters of the answer, or the failure reason
    started_at TEXT NOT NULL,  -- local time the run started
    finished_at TEXT,  -- local time the run ended
    FOREIGN KEY (task_id) REFERENCES scheduled_tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_task_runs_task_id ON task_runs(task_id);
CREATE INDEX IF NOT EXISTS idx_task_runs_started_at ON task_runs(started_at);
