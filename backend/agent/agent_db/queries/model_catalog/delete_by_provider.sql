-- Remove the synced model catalog rows of a provider.
DELETE FROM model_catalog WHERE provider = ?;
