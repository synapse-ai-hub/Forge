-- Current-month spend row of a provider/model pair.
SELECT cost_total FROM spend WHERE provider = ? AND model = ? AND month = ?;
