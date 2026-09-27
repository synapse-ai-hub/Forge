-- Model-specific spend limit configuration.
SELECT provider, model, limit_amount, created_at, updated_at
FROM spend_limits
WHERE provider = ? AND model = ?;
