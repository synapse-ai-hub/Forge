-- Compute the latency of one turn (seconds):
--   latency = SUM over steps of MAX(non-null total_time) for every row
--             EXCEPT the final assistant row and title rows
--             + time_to_first_token of the final assistant message.
-- Title rows are excluded: the title is generated in a background task
-- in parallel to the loop, so its time must not inflate turn latency.
-- Parallel calls share turn_number + step (they differ by substep): only
-- the maximum of the group counts, values are never summed.
-- NULL times are never taken as 0: a group whose values are all NULL
-- simply contributes nothing, the rest is still summed. When the final
-- assistant does not exist or its time_to_first_token is NULL, the whole
-- latency is NULL (the turn is skipped by AVG instead of counting 0).
SELECT
    (SELECT CASE WHEN SUM(mx) IS NULL THEN 0 ELSE SUM(mx) END
     FROM (
        SELECT MAX(m.total_time) AS mx
        FROM messages m
        WHERE m.session_id = ? AND m.turn_number = ?
          AND m.role <> 'title'
          AND NOT (m.role = 'assistant'
                   AND m.step = (SELECT MAX(a.step) FROM messages a
                                 WHERE a.role = 'assistant'
                                   AND a.session_id = ? AND a.turn_number = ?))
        GROUP BY m.step
     ))
    + (SELECT a2.time_to_first_token
       FROM messages a2
       WHERE a2.role = 'assistant'
         AND a2.session_id = ? AND a2.turn_number = ?
       ORDER BY a2.step DESC LIMIT 1);
