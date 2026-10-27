-- Key/value store of application settings persisted in the database (for example the global
-- advanced-parameter overrides and the last sync of each model catalog).
CREATE TABLE IF NOT EXISTS config_kv (
    key TEXT PRIMARY KEY,  -- name of the setting
    value TEXT  -- value of the setting, as text
);
