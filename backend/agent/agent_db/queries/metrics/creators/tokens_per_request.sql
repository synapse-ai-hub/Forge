-- Tokens per creator request in the time range (sum of its LLM calls).
-- {TIME_CLAUSE} : filter on created_at.
SELECT creator_id AS sid, SUM(total_tokens) AS value
FROM creators
WHERE role = 'call' AND creator_id IS NOT NULL {TIME_CLAUSE}
GROUP BY creator_id;
