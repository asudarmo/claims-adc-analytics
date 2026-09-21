-- One row per raw transaction, with every validation flag computed
-- explicitly (rather than dropped) so downstream models can split into
-- int_claims_transactions_valid / _quarantine without recomputing anything.
--
-- Dedup is keyed on amount_raw (the original text), not amount_numeric -
-- partitioning by the numeric cast would treat every non-numeric row
-- (amount_numeric = null) as one giant "duplicate" group, since SQL
-- collapses nulls together for PARTITION BY purposes.
--
-- Known interaction: is_date_out_of_bounds compares against the *imputed*
-- report_date from int_claims_header_clean, not the (unknown, since it's
-- missing) true one. When a claim's imputed report_date lands a little
-- later than its real first transaction, that transaction gets flagged here
-- even though nothing was actually wrong with it - an artifact of one rule
-- (report_date imputation) feeding another (date-bounds validation), not a
-- bug in either rule individually. Affects a couple of rows in practice;
-- left visible rather than fudged with a grace window that would just mask
-- the same underlying imputation uncertainty.
with txns as (
    select * from {{ ref('stg_claims_transactions') }}
),

headers as (
    select claim_id, report_date, rating_group from {{ ref('int_claims_header_clean') }}
),

deduped as (
    select
        t.*,
        row_number() over (
            partition by t.claim_id, t.transaction_date, t.transaction_type, t.amount_raw
            order by t.transaction_id
        ) as dedup_rank
    from txns t
),

flagged as (
    select
        d.*,
        h.report_date as header_report_date,
        h.rating_group,
        (h.claim_id is null) as is_orphan,
        (d.amount_numeric is null) as is_non_numeric,
        (d.transaction_type = 'Payment' and d.amount_numeric is not null and d.amount_numeric <= 0) as is_negative_or_zero_payment,
        (
            d.transaction_date > date '2025-12-31'
            or (h.report_date is not null and d.transaction_date < h.report_date)
        ) as is_date_out_of_bounds,
        (d.dedup_rank > 1) as is_duplicate
    from deduped d
    left join headers h on d.claim_id = h.claim_id
)

select
    *,
    not (is_orphan or is_non_numeric or is_negative_or_zero_payment or is_date_out_of_bounds or is_duplicate) as is_valid
from flagged
