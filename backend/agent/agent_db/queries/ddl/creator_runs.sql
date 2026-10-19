-- One row per run of a creator (agent, skill, tool or workflow creator).
-- kind: agent | skill | tool | workflow
-- action: question (asked the user for more information) | create | iterate |
--   exists (the item already existed, nothing was created)
-- status: success | error | aborted
-- item_name: name of the item created or modified, when known.
-- Tokens and cost add up every LLM call the run made. creator_calls keeps the
-- detail of each call; spend is not touched here.
CREATE TABLE IF NOT EXISTS creator_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    action TEXT,
    item_name TEXT,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'success',
    provider TEXT,
    model TEXT,
    llm_calls INTEGER NOT NULL DEFAULT 0,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    cost_input REAL NOT NULL DEFAULT 0.0,
    cost_output REAL NOT NULL DEFAULT 0.0,
    cost_total REAL NOT NULL DEFAULT 0.0,
    duration REAL,
    created_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_creator_runs_kind ON creator_runs(kind);
CREATE INDEX IF NOT EXISTS idx_creator_runs_created_at ON creator_runs(created_at);
