-- Seconds each turn took from the user message to the final answer.
CREATE TABLE IF NOT EXISTS turn_latency (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- internal row id
    session_id TEXT NOT NULL,  -- session of the turn
    turn_number INTEGER NOT NULL,  -- turn of the session
    latency REAL,  -- seconds of the whole turn
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_turn_latency_session_turn ON turn_latency(session_id, turn_number);
