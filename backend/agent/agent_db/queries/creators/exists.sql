-- Whether a creator conversation already has rows.
SELECT 1 FROM creators WHERE creator_id = ? LIMIT 1;
