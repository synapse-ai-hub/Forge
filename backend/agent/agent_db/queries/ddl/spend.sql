-- Monthly spend per provider and model: every LLM call adds to the row of its month
-- (llm_process and llm_streaming record it, success or failure).
CREATE TABLE IF NOT EXISTS spend (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- internal row id
    provider TEXT NOT NULL,  -- provider of the calls
    model TEXT NOT NULL,  -- model of the calls
    month TEXT NOT NULL,  -- month of the calls, YYYY-MM
    requests INTEGER DEFAULT 0,  -- number of calls
    prompt_tokens INTEGER DEFAULT 0,  -- input tokens
    completion_tokens INTEGER DEFAULT 0,  -- output tokens
    total_tokens INTEGER DEFAULT 0,  -- input + output tokens
    cost_input REAL DEFAULT 0.0,  -- USD cost of the input tokens
    cost_output REAL DEFAULT 0.0,  -- USD cost of the output tokens
    cost_total REAL DEFAULT 0.0,  -- cost_input + cost_output
    updated_at TEXT NOT NULL,  -- local time of the last call added
    UNIQUE(provider, model, month),
    FOREIGN KEY (provider) REFERENCES providers(provider)
);

CREATE INDEX IF NOT EXISTS idx_spend_provider_model ON spend(provider, model, month);
