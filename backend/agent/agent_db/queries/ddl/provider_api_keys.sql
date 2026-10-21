-- API key of each provider, stored encrypted. One row per provider.
CREATE TABLE IF NOT EXISTS provider_api_keys (
    provider TEXT PRIMARY KEY,  -- provider the key belongs to
    api_key_encrypted TEXT NOT NULL,  -- encrypted API key
    updated_at TEXT NOT NULL,  -- local time the key was saved
    FOREIGN KEY (provider) REFERENCES providers(provider)
);
