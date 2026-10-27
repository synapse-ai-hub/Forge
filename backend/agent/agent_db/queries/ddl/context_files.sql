-- Files the user loads as global context. Their content is added to the system prompt of
-- every conversation.
CREATE TABLE IF NOT EXISTS context_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- internal row id
    filename TEXT NOT NULL,  -- original file name
    content TEXT NOT NULL,  -- text of the file
    created_at TEXT NOT NULL  -- local time the file was loaded
);
