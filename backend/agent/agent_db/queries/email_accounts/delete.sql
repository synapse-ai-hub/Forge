-- Delete an email account by alias or email.
DELETE FROM email_accounts WHERE alias = ? COLLATE NOCASE OR email = ? COLLATE NOCASE;
