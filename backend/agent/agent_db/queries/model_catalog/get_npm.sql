-- models.dev npm package of a provider (resolves the API type).
SELECT npm FROM model_catalog WHERE provider = ? LIMIT 1;
