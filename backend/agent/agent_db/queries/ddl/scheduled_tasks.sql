CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    prompt TEXT NOT NULL,
    time TEXT NOT NULL DEFAULT '09:00',
    days TEXT NOT NULL DEFAULT '[0,1,2,3,4,5,6]',
    enabled INTEGER NOT NULL DEFAULT 1,
    repetitions TEXT,
    tool_permissions TEXT,
    skill_permissions TEXT,
    parameters TEXT,
    last_run_date TEXT,
    slot_runs TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
