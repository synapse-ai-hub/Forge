-- Cost (USD) per session, optionally filtered to one provider/model.
-- When a model filter is set, only that model's rows are summed within
-- each session. NULL and 0 cost_total (failed turn or model without rate)
-- are never counted: a 0 would pollute the average.
-- {TIME_CLAUSE} : filter on sessions.created_at.
-- {MODEL_CLAUSE} : optional filter on m.model / m.provider.
SELECT m.session_id AS sid, SUM(m.cost_total) AS value
FROM messages m
WHERE m.role = 'assistant'
  AND m.cost_total > 0
  AND m.session_id IN (
    SELECT session_id FROM sessions WHERE 1=1 {TIME_CLAUSE}
  )
  {MODEL_CLAUSE}
GROUP BY m.session_id
