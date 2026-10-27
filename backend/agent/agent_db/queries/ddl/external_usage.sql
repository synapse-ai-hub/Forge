-- Usage of services other than chat completions, such as the embeddings of a RAG query. The
-- provider column is free text (it can be unknown), so it has no foreign key.
CREATE TABLE IF NOT EXISTS external_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- internal row id
    kind TEXT NOT NULL,  -- kind of service, e.g. embedding
    provider TEXT NOT NULL,  -- provider of the service
    model TEXT NOT NULL,  -- model used
    units INTEGER DEFAULT 0,  -- number of calls
    prompt_tokens INTEGER DEFAULT 0,  -- input tokens
    completion_tokens INTEGER DEFAULT 0,  -- output tokens
    duration REAL,  -- seconds the call took
    session_id TEXT,  -- session that made the call, when there was one
    turn_number INTEGER,  -- turn of that session
    step INTEGER,  -- step of that turn
    created_at TEXT NOT NULL  -- local time, ISO format
);

CREATE INDEX IF NOT EXISTS idx_external_usage_kind ON external_usage(kind);
