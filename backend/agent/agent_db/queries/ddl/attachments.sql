-- Files the user attaches to a message. Deleted with the session.
-- No foreign key on purpose: creator conversations (creators table) have no
-- row in sessions, and their attachments use creator_id as session_id.
CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- internal row id
    session_id TEXT NOT NULL,  -- session of the message (or creator_id)
    turn_number INTEGER NOT NULL,  -- turn the file was attached to
    file_name TEXT NOT NULL,  -- original file name
    size INTEGER,  -- size in bytes
    content BLOB,  -- bytes of the file
    created_at TEXT NOT NULL  -- local time, ISO format
);

CREATE INDEX IF NOT EXISTS idx_attachments_session_turn
    ON attachments(session_id, turn_number);
