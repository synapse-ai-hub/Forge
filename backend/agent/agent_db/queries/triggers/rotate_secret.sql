-- Rotate the secret hash of a trigger, invalidating the previous one.
UPDATE triggers SET secret_hash = ?, updated_at = ? WHERE slug = ?;
