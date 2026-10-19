-- Close a creator run with what it did.
UPDATE creator_runs
SET action = ?, item_name = ?, status = ?, duration = ?, finished_at = ?
WHERE id = ?;
