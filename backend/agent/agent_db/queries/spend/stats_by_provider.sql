-- Current-month billing totals grouped by provider.
SELECT provider,
       SUM(requests) as requests,
       SUM(prompt_tokens) as prompt_tokens,
       SUM(completion_tokens) as completion_tokens,
       SUM(total_tokens) as total_tokens,
       SUM(cost_total) as cost
FROM spend
WHERE month = ?
GROUP BY provider
ORDER BY provider;
