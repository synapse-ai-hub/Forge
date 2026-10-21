-- Usage totals per provider and the limits the provider reports. The current code does not write
-- it: the billing statistics are computed from spend.
CREATE TABLE IF NOT EXISTS billing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- internal row id
    provider TEXT NOT NULL,  -- provider the totals belong to
    requests INTEGER DEFAULT 0,  -- number of LLM calls
    prompt_tokens INTEGER DEFAULT 0,  -- input tokens
    completion_tokens INTEGER DEFAULT 0,  -- output tokens
    total_tokens INTEGER DEFAULT 0,  -- input + output tokens
    cost REAL DEFAULT 0.0,  -- USD spent
    provider_limits TEXT,  -- JSON with the limits the provider reports
    created_at TEXT NOT NULL,  -- local time, ISO format
    updated_at TEXT NOT NULL,  -- local time of the last update
    UNIQUE(provider),
    FOREIGN KEY (provider) REFERENCES providers(provider)
);

CREATE INDEX IF NOT EXISTS idx_billing_provider ON billing(provider);
