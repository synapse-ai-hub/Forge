-- Model IDs of a provider (sorted).
SELECT model_id FROM model_catalog WHERE provider = ? ORDER BY model_id;
