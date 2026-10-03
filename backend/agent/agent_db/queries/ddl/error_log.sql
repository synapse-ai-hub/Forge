CREATE TABLE IF NOT EXISTS error_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    parent_id TEXT,
    turn_number INTEGER,
    exception TEXT NOT NULL,
    source TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_error_log_session_id ON error_log(session_id);
CREATE INDEX IF NOT EXISTS idx_error_log_created_at ON error_log(created_at);
