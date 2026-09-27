-- Cost totals (total/input/output, USD) in the time range.
-- {TIME_CLAUSE} : filter on messages.created_at.
SELECT SUM(cost_total) AS total,
       SUM(cost_input) AS cin,
       SUM(cost_output) AS cout
FROM messages
WHERE cost_total IS NOT NULL {TIME_CLAUSE};
