-- Active provider-level limit (model IS NULL).
SELECT limit_amount FROM spend_limits
WHERE provider = ? AND model IS NULL AND limit_amount > 0;
