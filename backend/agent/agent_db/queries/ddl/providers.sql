-- Cache of the LLM providers the application offers (google, openrouter, groq, LOCAL, ...).
-- Rows are upserted, never deleted. Most tables that hold a provider name point here.
CREATE TABLE IF NOT EXISTS providers (
    provider TEXT PRIMARY KEY,  -- provider id, e.g. google
    label TEXT NOT NULL,  -- name shown to the user
    models TEXT,  -- JSON list of the model ids the provider offers
    updated_at TEXT NOT NULL  -- local time of the last refresh
);
