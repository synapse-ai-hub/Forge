-- Every row of a creator conversation in order (loop-era rows carry turn/step).
SELECT * FROM creators WHERE creator_id = ? ORDER BY id;
