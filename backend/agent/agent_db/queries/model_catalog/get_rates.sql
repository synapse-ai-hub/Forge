-- Catalog cost rates (USD per million tokens) of a model.
SELECT cost_input, cost_output
FROM model_catalog
WHERE provider = ? AND model_id = ?;
