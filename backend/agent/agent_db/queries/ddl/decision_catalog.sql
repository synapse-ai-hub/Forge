-- Catalog of the decision models, synced from models.dev (type=decision) for any provider. It
-- has the same columns as model_catalog; its providers are not necessarily configured, so it
-- has no foreign key to providers. calculate_cost falls back to it when a model is not in
-- model_catalog.
CREATE TABLE IF NOT EXISTS decision_catalog (
    provider TEXT NOT NULL,  -- provider that serves the model
    model_id TEXT NOT NULL,  -- id of the model for that provider
    type TEXT,  -- kind of model (chat, embedding, ...)
    name TEXT,  -- name shown to the user
    description TEXT,  -- short description
    family TEXT,  -- family of the model
    context_window INTEGER,  -- tokens of context the model accepts
    input_limit INTEGER,  -- maximum input tokens
    output_limit INTEGER,  -- maximum output tokens
    reasoning INTEGER DEFAULT 0,  -- 1 if the model reasons
    reasoning_options TEXT,  -- JSON with the reasoning levels it accepts
    tool_call INTEGER DEFAULT 0,  -- 1 if it supports tool calling
    attachment INTEGER DEFAULT 0,  -- 1 if it accepts attachments
    temperature INTEGER DEFAULT 0,  -- 1 if the temperature can be set
    structured_output INTEGER DEFAULT 0,  -- 1 if it supports structured output
    modalities_input TEXT,  -- JSON list of the input modalities (text, image, ...)
    modalities_output TEXT,  -- JSON list of the output modalities
    cost_input REAL,  -- USD per million input tokens
    cost_output REAL,  -- USD per million output tokens
    cost_cache_read REAL,  -- USD per million cached input tokens read
    cost_cache_write REAL,  -- USD per million cached input tokens written
    open_weights INTEGER DEFAULT 0,  -- 1 if the weights are open
    status TEXT,  -- lifecycle status of the model (beta, deprecated, ...)
    api TEXT,  -- API base URL of the provider
    npm TEXT,  -- SDK package the provider documents
    updated_at TEXT NOT NULL,  -- local time of the last refresh
    PRIMARY KEY (provider, model_id)
);

CREATE INDEX IF NOT EXISTS idx_decision_catalog_provider ON decision_catalog(provider);
CREATE INDEX IF NOT EXISTS idx_decision_catalog_model ON decision_catalog(model_id);
CREATE INDEX IF NOT EXISTS idx_decision_catalog_type ON decision_catalog(type);
