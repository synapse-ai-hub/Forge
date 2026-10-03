-- Encrypt and store the API key of a provider (upsert).
INSERT INTO provider_api_keys (provider, api_key_encrypted, updated_at)
VALUES (?, ?, ?)
ON CONFLICT(provider) DO UPDATE SET
    api_key_encrypted = excluded.api_key_encrypted,
    updated_at = excluded.updated_at;
