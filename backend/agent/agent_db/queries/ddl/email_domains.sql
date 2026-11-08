-- Email domain settings cache. One row per domain, reused by all accounts.
CREATE TABLE IF NOT EXISTS email_domains (
    domain TEXT PRIMARY KEY,
    imap_server TEXT,
    imap_port INTEGER DEFAULT 993,
    smtp_server TEXT,
    smtp_port INTEGER DEFAULT 587,
    provider TEXT,
    source TEXT DEFAULT 'preset',
    updated_at TEXT NOT NULL
);
