-- Get email domain settings by domain.
SELECT domain, imap_server, imap_port, smtp_server, smtp_port, provider, source, updated_at FROM email_domains WHERE domain = ? LIMIT 1;
