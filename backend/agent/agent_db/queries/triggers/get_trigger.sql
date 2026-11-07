-- Get one trigger by slug, with its mapped workflow and state.
SELECT slug, workflow_name, enabled, created_at, updated_at FROM triggers WHERE slug = ?;
