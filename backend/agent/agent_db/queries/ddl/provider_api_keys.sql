CREATE TABLE IF NOT EXISTS provider_api_keys (
    provider TEXT PRIMARY KEY,
    api_key_encrypted TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
