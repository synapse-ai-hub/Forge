-- Compute the latency of one creator turn (seconds):
--   latency = SUM over steps of MAX(non-null total_time) for every row
--             EXCEPT the final assistant row and the result/call rows
--             + time_to_first_token of the final assistant message.
-- Mirrors turn_latency/compute.sql, which only reads the messages table.
-- Parallel calls share turn_number + step (they differ by substep): only
-- the maximum of the group counts, values are never summed.
SELECT
    (SELECT CASE WHEN SUM(mx) IS NULL THEN 0 ELSE SUM(mx) END
     FROM (
        SELECT MAX(m.total_time) AS mx
        FROM creators m
        WHERE m.creator_id = ? AND m.turn_number = ?
          AND m.role NOT IN ('result', 'call')
          AND NOT (m.role = 'assistant'
                   AND m.step = (SELECT MAX(a.step) FROM creators a
                                 WHERE a.role = 'assistant'
                                   AND a.creator_id = ? AND a.turn_number = ?))
        GROUP BY m.step
     ))
    + (SELECT a2.time_to_first_token
       FROM creators a2
       WHERE a2.role = 'assistant'
         AND a2.creator_id = ? AND a2.turn_number = ?
       ORDER BY a2.step DESC LIMIT 1);
