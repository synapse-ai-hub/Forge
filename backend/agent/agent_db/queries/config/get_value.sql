-- Read a value from the key-value config store.
SELECT value FROM config_kv WHERE key = ?;
