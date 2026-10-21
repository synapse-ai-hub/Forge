-- Thumbs up / down the user gives to an assistant answer. One row per answer
-- (a turn of a session); clicking again removes it. model and provider are the
-- ones that produced the answer, so feedback can later be read per model.
CREATE TABLE IF NOT EXISTS message_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- internal row id
    session_id TEXT NOT NULL,  -- session of the answer
    turn_number INTEGER NOT NULL,  -- turn of the answer
    feedback_type TEXT NOT NULL CHECK (feedback_type IN ('up', 'down')),  -- up | down
    model TEXT,  -- model that produced the answer
    provider TEXT,  -- provider of that model
    created_at TEXT NOT NULL,  -- local time the feedback was given
    updated_at TEXT NOT NULL,  -- local time of the last change
    UNIQUE (session_id, turn_number),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_message_feedback_created_at ON message_feedback(created_at);
