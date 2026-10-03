-- All spend limit configurations.
SELECT provider, model, limit_amount, created_at, updated_at
FROM spend_limits
ORDER BY provider, model;
