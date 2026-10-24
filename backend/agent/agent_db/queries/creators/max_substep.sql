-- Highest substep of a creator turn step (parallel tool calls share turn + step).
SELECT MAX(substep) AS max_substep FROM creators
WHERE creator_id = ? AND turn_number = ? AND step = ?;
