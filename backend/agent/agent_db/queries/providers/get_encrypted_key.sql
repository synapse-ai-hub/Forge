-- Encrypted API key of a provider (decrypted backend-side only).
SELECT api_key_encrypted FROM provider_api_keys WHERE provider = ?;
