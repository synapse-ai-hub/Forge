-- Compute the latency of one turn (seconds):
--   SUM(assistant total_time of non-final steps)
--   + SUM over steps of MAX(tool total_time)
--   + time_to_first_token of the final assistant message.
-- Each part is COALESCEd to 0 so a missing part (direct answer with no
-- tool steps) does not null out the other parts.
SELECT
    COALESCE((SELECT SUM(a.total_time) FROM messages a
        WHERE a.role = 'assistant' AND a.session_id = ? AND a.turn_number = ?
        AND a.step < (SELECT MAX(m.step) FROM messages m
            WHERE m.role = 'assistant' AND m.session_id = ? AND m.turn_number = ?)), 0)
    + COALESCE((SELECT SUM(mx) FROM (SELECT MAX(t2.total_time) AS mx FROM messages t2
        WHERE t2.role = 'tool' AND t2.session_id = ? AND t2.turn_number = ?
        GROUP BY t2.step)), 0)
    + COALESCE((SELECT m2.time_to_first_token FROM messages m2
        WHERE m2.role = 'assistant' AND m2.session_id = ? AND m2.turn_number = ?
        ORDER BY m2.step DESC LIMIT 1), 0);
