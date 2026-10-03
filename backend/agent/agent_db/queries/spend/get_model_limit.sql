-- Active model-specific limit for a provider/model pair.
SELECT limit_amount FROM spend_limits
WHERE provider = ? AND model = ? AND limit_amount > 0;
