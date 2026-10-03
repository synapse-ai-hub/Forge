-- Aggregated billing totals of a provider for the current month.
SELECT SUM(requests) as requests,
       SUM(prompt_tokens) as prompt_tokens,
       SUM(completion_tokens) as completion_tokens,
       SUM(total_tokens) as total_tokens,
       SUM(cost_total) as cost
FROM spend
WHERE provider = ? AND month = ?;
