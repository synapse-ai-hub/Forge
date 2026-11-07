-- Enable or disable a trigger without deleting its history.
UPDATE triggers SET enabled = ?, updated_at = ? WHERE slug = ?;
