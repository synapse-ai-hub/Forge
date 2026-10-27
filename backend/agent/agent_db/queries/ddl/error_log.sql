-- Errors the application caught, with the session and turn that were running. It has no
-- foreign key on purpose: an error must be stored even when its session does not exist
-- (anymore) and it must outlive the session.
CREATE TABLE IF NOT EXISTS error_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- internal row id
    session_id TEXT,  -- session that was running, when there was one
    parent_id TEXT,  -- parent session of that session
    turn_number INTEGER,  -- turn that was running
    exception TEXT NOT NULL,  -- error message
    source TEXT,  -- where it was caught (file:function)
    created_at TEXT NOT NULL  -- local time, ISO format
);

CREATE INDEX IF NOT EXISTS idx_error_log_session_id ON error_log(session_id);
CREATE INDEX IF NOT EXISTS idx_error_log_created_at ON error_log(created_at);
