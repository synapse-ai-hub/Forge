-- Current-month spend rows of a provider joined with catalog rates.
SELECT s.provider, s.model, s.requests, s.prompt_tokens,
       s.completion_tokens, s.total_tokens, s.cost_input,
       s.cost_output, s.cost_total, s.updated_at,
       c.cost_input AS cost_input_rate,
       c.cost_output AS cost_output_rate
FROM spend s LEFT JOIN model_catalog c
  ON c.provider = s.provider AND c.model_id = s.model
WHERE s.provider = ? AND s.month = ?
ORDER BY s.updated_at DESC;
