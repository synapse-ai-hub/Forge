-- Highest turn of a creator conversation (0 when it has no loop-era rows).
SELECT MAX(turn_number) AS max_turn FROM creators WHERE creator_id = ?;
