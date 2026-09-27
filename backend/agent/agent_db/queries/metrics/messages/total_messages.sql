-- Total messages (turns) in the time range. A message is one turn, not
-- one row of the messages table (rows also hold tool/reasoning steps).
-- {TIME_CLAUSE} : filter on messages.created_at.
SELECT COUNT(*) AS cnt
FROM (
    SELECT DISTINCT m.session_id, m.turn_number
    FROM messages m
    WHERE 1=1 {TIME_CLAUSE}
) AS turns;
