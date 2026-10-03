CREATE TABLE IF NOT EXISTS spend_limits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    model TEXT,
    limit_amount REAL NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(provider, model)
);

CREATE INDEX IF NOT EXISTS idx_spend_limits_provider_model ON spend_limits(provider, model);
