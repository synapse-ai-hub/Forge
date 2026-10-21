-- Tasks the scheduler runs on its own: a prompt an agent executes at a time of the day.
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id TEXT PRIMARY KEY,  -- task id
    name TEXT NOT NULL,  -- name shown to the user
    prompt TEXT NOT NULL,  -- what the agent has to do
    time TEXT NOT NULL DEFAULT '09:00',  -- main time of the day, HH:MM
    days TEXT NOT NULL DEFAULT '[0,1,2,3,4,5,6]',  -- JSON list of the weekdays it runs (0 = Sunday, 1 = Monday, ...)
    enabled INTEGER NOT NULL DEFAULT 1,  -- 1 active, 0 paused
    repetitions TEXT,  -- JSON list of extra slots [{"time": "HH:MM", "days": [0..6]}]
    tool_permissions TEXT,  -- JSON with the tools the run may use
    skill_permissions TEXT,  -- JSON with the skills the run may use
    parameters TEXT,  -- JSON with the model parameters of the run
    last_run_date TEXT,  -- date of the last execution of the main slot
    slot_runs TEXT,  -- JSON map slot -> date of its last execution
    created_at TEXT NOT NULL,  -- local time, ISO format
    updated_at TEXT NOT NULL  -- local time of the last edit
);
