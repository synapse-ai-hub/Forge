-- Get a single email account by alias or email (full row, includes encrypted password).
SELECT alias, email, password_encrypted, imap_server, imap_port, smtp_server, smtp_port, provider, last_status, last_error, updated_at FROM email_accounts WHERE alias = ? COLLATE NOCASE OR email = ? COLLATE NOCASE LIMIT 1;
