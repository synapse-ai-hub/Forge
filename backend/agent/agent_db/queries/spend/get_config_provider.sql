-- Provider-level spend limit configuration.
SELECT provider, model, limit_amount, created_at, updated_at
FROM spend_limits
WHERE provider = ? AND model IS NULL;
