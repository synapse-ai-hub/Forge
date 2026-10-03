CREATE TABLE IF NOT EXISTS spend (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    month TEXT NOT NULL,
    requests INTEGER DEFAULT 0,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    cost_input REAL DEFAULT 0.0,
    cost_output REAL DEFAULT 0.0,
    cost_total REAL DEFAULT 0.0,
    updated_at TEXT NOT NULL,
    UNIQUE(provider, model, month)
);

CREATE INDEX IF NOT EXISTS idx_spend_provider_model ON spend(provider, model, month);
