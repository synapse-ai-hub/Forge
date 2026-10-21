-- Frontier of unsettled work units for the current step.
-- One row per dispatched tool call, written at dispatch time (state 'open')
-- and flipped to 'done' when its result commits. Rows are only deleted when
-- the step closes with a validated done signal; a cut flow leaves them behind
-- so the next turn can resume from them.
CREATE TABLE IF NOT EXISTS step_frontier (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- internal row id
    session_id TEXT NOT NULL,  -- session of the turn
    turn_number INTEGER NOT NULL,  -- turn the call belongs to
    step INTEGER NOT NULL DEFAULT 0,  -- step of the turn
    substep INTEGER NOT NULL DEFAULT 0,  -- position inside the step
    tool_call_id TEXT,  -- id of the tool call
    tool_name TEXT NOT NULL,  -- tool that was called
    tool_args TEXT,  -- JSON with the arguments of the call
    state TEXT NOT NULL DEFAULT 'open',  -- open (dispatched) | done (result committed)
    child_id TEXT,  -- session_id of the sub-agent, when the call was a task
    created_at TEXT NOT NULL,  -- local time the call was dispatched
    updated_at TEXT NOT NULL,  -- local time of the last change
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_step_frontier_session_turn ON step_frontier(session_id, turn_number);
