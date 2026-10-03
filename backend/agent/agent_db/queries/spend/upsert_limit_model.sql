-- Upsert a model-specific spend limit.
INSERT INTO spend_limits
(provider, model, limit_amount, created_at, updated_at)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(provider, model) DO UPDATE SET
    limit_amount = excluded.limit_amount,
    updated_at = excluded.updated_at;
