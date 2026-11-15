-- Search models by id, name or description substring
-- (case-insensitive). LIKE patterns are passed as parameters
-- (already escaped by the caller).
SELECT provider, model_id, type, modalities_output
FROM model_catalog
WHERE model_id LIKE ? ESCAPE '\'
   OR name LIKE ? ESCAPE '\'
   OR description LIKE ? ESCAPE '\'
ORDER BY provider, model_id;
