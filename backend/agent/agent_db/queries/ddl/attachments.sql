-- Files the user attaches to a message. Deleted with the session.
CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- internal row id
    session_id TEXT NOT NULL,  -- session of the message
    turn_number INTEGER NOT NULL,  -- turn the file was attached to
    file_name TEXT NOT NULL,  -- original file name
    size INTEGER,  -- size in bytes
    content BLOB,  -- bytes of the file
    created_at TEXT NOT NULL,  -- local time, ISO format
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_attachments_session_turn
    ON attachments(session_id, turn_number);
