-- User message content of a given turn (resume context source, creators table).
SELECT content FROM creators
WHERE creator_id = ? AND role = 'user' AND turn_number = ?
ORDER BY id ASC LIMIT 1;
