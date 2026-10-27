-- Chat sessions. A root session is a conversation shown in the sidebar; a child session
-- (parent_id set) belongs to a sub-agent called with task or to a node of a workflow run.
-- Deleting a session deletes its children and everything that hangs from it.
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- internal row id
    session_id TEXT UNIQUE NOT NULL,  -- public id of the session (the one the API and the other tables use)
    created_at TEXT NOT NULL,  -- local time, ISO format
    updated_at TEXT NOT NULL,  -- local time of the last message; orders the sidebar
    metadata TEXT,  -- JSON object with free data of the origin, e.g. {"source": "workflow"} (workflow, scheduler, review)
    title TEXT,  -- title shown in the sidebar
    parent_id TEXT,  -- session_id of the parent session (NULL for root sessions)
    FOREIGN KEY (parent_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sessions_parent_id ON sessions(parent_id);
