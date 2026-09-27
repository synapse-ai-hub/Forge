-- Create the provider-level limit when it does not exist yet.
INSERT INTO spend_limits
(provider, model, limit_amount, created_at, updated_at)
VALUES (?, NULL, ?, ?, ?);
