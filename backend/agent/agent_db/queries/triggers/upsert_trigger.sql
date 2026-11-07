-- Create a trigger with slug, mapped workflow and secret hash, enabled by default.
-- Duplicate slug fails with UNIQUE constraint, mapped to 409 by the service layer.
INSERT INTO triggers (slug, workflow_name, secret_hash, enabled, created_at, updated_at)
VALUES (?, ?, ?, 1, ?, ?);
