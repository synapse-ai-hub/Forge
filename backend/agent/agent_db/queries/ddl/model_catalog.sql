CREATE TABLE IF NOT EXISTS model_catalog (
    provider TEXT NOT NULL,
    model_id TEXT NOT NULL,
    name TEXT,
    description TEXT,
    family TEXT,
    context_window INTEGER,
    input_limit INTEGER,
    output_limit INTEGER,
    reasoning INTEGER DEFAULT 0,
    reasoning_options TEXT,
    tool_call INTEGER DEFAULT 0,
    attachment INTEGER DEFAULT 0,
    temperature INTEGER DEFAULT 0,
    structured_output INTEGER DEFAULT 0,
    modalities_input TEXT,
    modalities_output TEXT,
    cost_input REAL,
    cost_output REAL,
    cost_cache_read REAL,
    cost_cache_write REAL,
    open_weights INTEGER DEFAULT 0,
    status TEXT,
    api TEXT,
    npm TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE(provider, model_id)
);

CREATE INDEX IF NOT EXISTS idx_model_catalog_provider ON model_catalog(provider);
CREATE INDEX IF NOT EXISTS idx_model_catalog_model ON model_catalog(model_id);
CREATE INDEX IF NOT EXISTS idx_model_catalog_reasoning ON model_catalog(reasoning);
CREATE INDEX IF NOT EXISTS idx_model_catalog_context ON model_catalog(context_window);
