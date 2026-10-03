-- Average total time per turn: mean over (session, turn) groups of the
-- summed total_time of the turn's rows.
-- {TIME_CLAUSE} : filter on messages.created_at.
SELECT AVG(turn_total) AS avg FROM (
    SELECT SUM(total_time) AS turn_total
    FROM messages
    WHERE total_time IS NOT NULL AND turn_number IS NOT NULL {TIME_CLAUSE}
    GROUP BY session_id, turn_number
);
