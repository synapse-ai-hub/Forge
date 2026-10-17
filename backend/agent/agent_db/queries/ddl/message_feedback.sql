-- Thumbs up / down the user gives to an assistant answer. One row per answer
-- (a turn of a session); clicking again removes it. model and provider are the
-- ones that produced the answer, so feedback can later be read per model.
CREATE TABLE IF NOT EXISTS message_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL,
    feedback_type TEXT NOT NULL CHECK (feedback_type IN ('up', 'down')),
    model TEXT,
    provider TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (session_id, turn_number),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_message_feedback_created_at ON message_feedback(created_at);
