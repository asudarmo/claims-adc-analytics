-- Views backing the Great Expectations checks in scripts/gx_validate_raw.py.
--
-- These exist as real views (not inline GX query assets) because GX's
-- unexpected_index_query feature substitutes an asset's defining SQL
-- directly after "FROM", which is only valid when that SQL is a bare
-- table/view reference - an inline "SELECT ... FROM (SELECT ...)" query
-- asset produces invalid SQL ("FROM SELECT ...") when GX tries to build the
-- full-recall query. Backing each cross-table/derived check with a named
-- view sidesteps that entirely.

CREATE SCHEMA IF NOT EXISTS checks;

CREATE OR REPLACE VIEW checks.transactions_with_header AS
SELECT t.transaction_id, t.claim_id, t.transaction_date, t.transaction_type,
       t.amount, h.claim_id AS header_claim_id, h.report_date, h.rating_group
FROM raw.claims_transactions t
LEFT JOIN raw.claims_header h ON t.claim_id = h.claim_id;

CREATE OR REPLACE VIEW checks.payments_numeric AS
SELECT transaction_id, claim_id, amount::numeric AS amount_numeric
FROM raw.claims_transactions
WHERE transaction_type = 'Payment' AND amount ~ '^-?\d+(\.\d+)?$';

CREATE OR REPLACE VIEW checks.date_violations AS
SELECT t.transaction_id, t.claim_id, t.transaction_date, h.report_date
FROM raw.claims_transactions t
JOIN raw.claims_header h ON t.claim_id = h.claim_id
WHERE t.transaction_date > DATE '2025-12-31' OR t.transaction_date < h.report_date;

CREATE OR REPLACE VIEW checks.duplicate_transaction_groups AS
SELECT claim_id, transaction_date, transaction_type, amount, count(*) AS n,
       array_agg(transaction_id) AS transaction_ids
FROM raw.claims_transactions
GROUP BY claim_id, transaction_date, transaction_type, amount
HAVING count(*) > 1;

CREATE OR REPLACE VIEW checks.payment_log_zscore AS
SELECT t.transaction_id, t.claim_id,
       (LN(t.amount::numeric) - AVG(LN(t.amount::numeric)) OVER (PARTITION BY h.rating_group))
         / NULLIF(STDDEV(LN(t.amount::numeric)) OVER (PARTITION BY h.rating_group), 0) AS log_z
FROM raw.claims_transactions t
JOIN raw.claims_header h ON t.claim_id = h.claim_id
WHERE t.transaction_type = 'Payment' AND t.amount ~ '^-?\d+(\.\d+)?$' AND t.amount::numeric > 0;

CREATE OR REPLACE VIEW checks.earned_premium_keyed AS
SELECT *, accident_year || '-' || rating_group AS key FROM raw.earned_premium;

CREATE OR REPLACE VIEW checks.rate_changes_keyed AS
SELECT *, accident_year || '-' || rating_group AS key FROM raw.rate_changes;
