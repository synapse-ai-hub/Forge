-- Decision model IDs of a provider (sorted).
SELECT model_id FROM decision_catalog WHERE provider = ? ORDER BY model_id;
