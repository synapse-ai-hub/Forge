-- Catalog of the models of the configured providers (models.dev): limits, capabilities and
-- prices. calculate_cost reads the prices from here.
CREATE TABLE IF NOT EXISTS model_catalog (
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
    PRIMARY KEY (provider, model_id),
    FOREIGN KEY (provider) REFERENCES providers(provider)
);

CREATE INDEX IF NOT EXISTS idx_model_catalog_provider ON model_catalog(provider);
CREATE INDEX IF NOT EXISTS idx_model_catalog_model ON model_catalog(model_id);
CREATE INDEX IF NOT EXISTS idx_model_catalog_reasoning ON model_catalog(reasoning);
CREATE INDEX IF NOT EXISTS idx_model_catalog_context ON model_catalog(context_window);
