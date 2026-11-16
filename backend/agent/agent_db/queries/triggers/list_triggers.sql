-- List triggers paginated by slug, without secrets.
SELECT slug, workflow_name, enabled, created_at, updated_at FROM triggers ORDER BY slug LIMIT ? OFFSET ?;
