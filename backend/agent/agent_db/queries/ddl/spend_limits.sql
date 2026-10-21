-- Monthly spend limit the user sets for a provider (model NULL) or for one of its models.
CREATE TABLE IF NOT EXISTS spend_limits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- internal row id
    provider TEXT NOT NULL,  -- provider the limit applies to
    model TEXT,  -- model the limit applies to; NULL means the whole provider
    limit_amount REAL NOT NULL,  -- monthly limit in USD
    created_at TEXT NOT NULL,  -- local time, ISO format
    updated_at TEXT NOT NULL,  -- local time of the last edit
    UNIQUE(provider, model),
    FOREIGN KEY (provider) REFERENCES providers(provider)
);

CREATE INDEX IF NOT EXISTS idx_spend_limits_provider_model ON spend_limits(provider, model);
