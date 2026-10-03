-- Accumulate a spend transaction into the current month's row.
UPDATE spend
SET requests = requests + ?,
    prompt_tokens = prompt_tokens + ?,
    completion_tokens = completion_tokens + ?,
    total_tokens = total_tokens + ?,
    cost_input = cost_input + ?,
    cost_output = cost_output + ?,
    cost_total = cost_total + ?,
    updated_at = ?
WHERE provider = ? AND model = ? AND month = ?;
