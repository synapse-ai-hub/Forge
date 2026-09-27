-- Remove the stored API key of a provider.
DELETE FROM provider_api_keys WHERE provider = ?;
