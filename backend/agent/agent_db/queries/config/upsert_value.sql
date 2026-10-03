-- Upsert a key-value config pair.
INSERT INTO config_kv (key, value) VALUES (?, ?)
ON CONFLICT(key) DO UPDATE SET value = excluded.value;
