-- Get the secret hash of a trigger for inbound verification. Backend only, never exposed.
SELECT secret_hash FROM triggers WHERE slug = ?;
