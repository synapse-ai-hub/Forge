-- Current-month spend total of a provider (all its models).
SELECT SUM(cost_total) as total_cost FROM spend WHERE provider = ? AND month = ?;
