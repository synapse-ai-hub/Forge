-- Upsert an email account by alias.
INSERT INTO email_accounts (alias, email, password_encrypted, imap_server, imap_port, smtp_server, smtp_port, provider, last_status, last_error, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(alias) DO UPDATE SET
email = excluded.email, password_encrypted = excluded.password_encrypted, imap_server = excluded.imap_server, imap_port = excluded.imap_port, smtp_server = excluded.smtp_server, smtp_port = excluded.smtp_port, provider = excluded.provider, last_status = excluded.last_status, last_error = excluded.last_error, updated_at = excluded.updated_at;
