-- Upsert email domain settings by domain.
INSERT INTO email_domains (domain, imap_server, imap_port, smtp_server, smtp_port, provider, source, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(domain) DO UPDATE SET
imap_server = excluded.imap_server, imap_port = excluded.imap_port, smtp_server = excluded.smtp_server, smtp_port = excluded.smtp_port, provider = excluded.provider, source = excluded.source, updated_at = excluded.updated_at;
