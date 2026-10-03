CREATE TABLE IF NOT EXISTS providers (
    provider TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    models TEXT,
    updated_at TEXT NOT NULL
);
