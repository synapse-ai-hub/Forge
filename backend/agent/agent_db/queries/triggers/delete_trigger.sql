-- Delete a trigger. Runs stay for audit under the current retention policy.
DELETE FROM triggers WHERE slug = ?;
