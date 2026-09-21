-- Grain: one row per valid transaction. Drill-through detail behind fct_claim
-- and fct_triangle_cell.
select
    t.transaction_id,
    t.claim_id,
    h.rating_group,
    h.accident_year,
    t.transaction_date,
    t.transaction_type,
    t.amount
from {{ ref('int_claims_transactions_valid') }} t
join {{ ref('int_claims_header_clean') }} h on t.claim_id = h.claim_id
