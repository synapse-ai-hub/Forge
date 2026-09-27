CREATE TABLE IF NOT EXISTS creator_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    caller TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    total_time REAL,
    cost_input REAL DEFAULT 0.0,
    cost_output REAL DEFAULT 0.0,
    cost_total REAL DEFAULT 0.0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_creator_calls_caller ON creator_calls(caller);
