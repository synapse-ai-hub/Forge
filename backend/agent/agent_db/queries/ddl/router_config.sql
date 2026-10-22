-- Router permissions edited in the sidebar panel. Single row (id = 1); each column holds a JSON
-- array of allowed names. No row (or all columns empty) means the floor defaults.
CREATE TABLE IF NOT EXISTS router_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- always 1: single-row table
    agentes TEXT NOT NULL DEFAULT '[]',  -- JSON array of allowed sub-agent names
    tools TEXT NOT NULL DEFAULT '[]',  -- JSON array of allowed tool names
    skills TEXT NOT NULL DEFAULT '[]',  -- JSON array of allowed skill names
    rag TEXT NOT NULL DEFAULT '[]',  -- JSON array of allowed RAG collection names
    updated_at TEXT NOT NULL  -- local time of the last change
);
