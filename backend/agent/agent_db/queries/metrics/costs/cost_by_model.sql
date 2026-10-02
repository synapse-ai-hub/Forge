-- Total/input/output cost (USD) per provider/model in the time range.
-- Rows with NULL or 0 cost (failed turn or model without rate) are excluded:
-- a 0 is never a real cost and would pollute averages.
-- {TIME_CLAUSE} : filter on messages.created_at.
SELECT provider, model,
       SUM(cost_total) AS total,
       SUM(cost_input) AS input,
       SUM(cost_output) AS output
FROM messages
WHERE role = 'assistant'
    AND model IS NOT NULL AND model != ''
    AND provider IS NOT NULL AND provider != ''
    AND cost_total > 0 {TIME_CLAUSE}
GROUP BY provider, model
ORDER BY total DESC;
