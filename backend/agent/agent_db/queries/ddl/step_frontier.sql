-- Frontier of unsettled work units for the current step.
-- One row per dispatched tool call, written at dispatch time (state 'open')
-- and flipped to 'done' when its result commits. Rows are only deleted when
-- the step closes with a validated done signal; a cut flow leaves them behind
-- so the next turn can resume from them.
CREATE TABLE IF NOT EXISTS step_frontier (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL,
    step INTEGER NOT NULL DEFAULT 0,
    substep INTEGER NOT NULL DEFAULT 0,
    tool_call_id TEXT,
    tool_name TEXT NOT NULL,
    tool_args TEXT,
    state TEXT NOT NULL DEFAULT 'open',
    child_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_step_frontier_session_turn ON step_frontier(session_id, turn_number);
