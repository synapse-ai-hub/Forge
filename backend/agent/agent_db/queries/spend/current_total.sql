-- Current-month spend total of a provider.
SELECT SUM(cost_total) as total FROM spend WHERE provider = ? AND month = ?;
