-- Every message of every session: what the user wrote, what the model answered, the tool
-- results and the verdicts of the decision model. One row per message, with the tokens,
-- time and cost of the LLM call that produced it. A turn is one user message and all the
-- steps the agent takes to answer it.
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- internal row id; orders the messages
    session_id TEXT NOT NULL,  -- session the message belongs to
    role TEXT NOT NULL,  -- system | user | assistant | tool | title | decisor (verdict of the decision model)
    content TEXT,  -- text of the message
    reasoning TEXT,  -- reasoning of the model, when it produced one
    tool_calls TEXT,  -- JSON list of the tool calls the assistant requested
    tool_results TEXT,  -- JSON list of the results of those calls
    status TEXT,  -- success | error, for assistant messages
    message TEXT,  -- plain description of the error when status is error
    prompt_tokens INTEGER,  -- input tokens of the LLM call
    completion_tokens INTEGER,  -- output tokens of the LLM call
    total_tokens INTEGER,  -- prompt_tokens + completion_tokens
    total_time REAL,  -- seconds the call took
    time_to_first_token REAL,  -- seconds until the first token arrived
    tool_call_id TEXT,  -- id of the tool call, in tool messages
    tool_name TEXT,  -- name of the tool, in tool messages
    model TEXT,  -- model that produced the message
    provider TEXT,  -- provider of that model
    cost_input REAL,  -- USD cost of the input tokens
    cost_output REAL,  -- USD cost of the output tokens
    cost_total REAL,  -- cost_input + cost_output
    turn_number INTEGER,  -- turn of the session (1, 2, ...)
    step INTEGER DEFAULT 0,  -- step inside the turn (one per LLM round)
    substep INTEGER DEFAULT 0,  -- position inside the step (parallel tool calls)
    created_at TEXT NOT NULL,  -- local time, ISO format
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
