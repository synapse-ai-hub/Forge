-- Decision catalog cost rates (USD per million tokens) of a model.
SELECT cost_input, cost_output
FROM decision_catalog
WHERE provider = ? AND model_id = ?;
