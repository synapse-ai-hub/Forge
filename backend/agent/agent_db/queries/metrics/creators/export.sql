-- Creator requests in the time range (CSV export, one row per request).
-- {TIME_CLAUSE} : filter on created_at.
SELECT creator_id, kind, status, action, item_name, provider, model, total_tokens, total_time, cost_total, created_at
FROM creators
WHERE role = 'result' {TIME_CLAUSE}
ORDER BY created_at ASC;
