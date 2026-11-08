-- List email accounts without passwords.
SELECT alias, email, imap_server, imap_port, smtp_server, smtp_port, provider, last_status, last_error, updated_at FROM email_accounts ORDER BY alias;
