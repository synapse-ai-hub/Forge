-- Upsert a provider row in the cache.
INSERT INTO providers (provider, label, models, updated_at)
VALUES (?, ?, ?, ?)
ON CONFLICT(provider) DO UPDATE SET
label = excluded.label, models = excluded.models,
updated_at = excluded.updated_at;
