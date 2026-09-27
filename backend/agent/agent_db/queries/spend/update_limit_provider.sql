-- Update the provider-level limit (model IS NULL).
UPDATE spend_limits
SET limit_amount = ?, updated_at = ?
WHERE provider = ? AND model IS NULL;
