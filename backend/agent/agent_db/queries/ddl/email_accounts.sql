-- Email accounts configured from the UI. One row per mailbox, no .env usage.
CREATE TABLE IF NOT EXISTS email_accounts (
    alias TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_encrypted TEXT NOT NULL,
    imap_server TEXT,
    imap_port INTEGER DEFAULT 993,
    smtp_server TEXT,
    smtp_port INTEGER DEFAULT 587,
    provider TEXT,
    last_status TEXT DEFAULT 'pending',
    last_error TEXT,
    updated_at TEXT NOT NULL
);
