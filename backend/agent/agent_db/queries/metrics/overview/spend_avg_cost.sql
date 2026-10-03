-- Average recorded cost per provider/model row in the spend table
-- (denominator side of avg_cost_per_provider_model).
-- {TIME_CLAUSE} : filter on spend.updated_at.
SELECT AVG(cost_total) AS avg
FROM spend
WHERE cost_total > 0 {TIME_CLAUSE};
