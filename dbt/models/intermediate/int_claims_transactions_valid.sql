select
    transaction_id,
    claim_id,
    transaction_date,
    transaction_type,
    amount_numeric as amount,
    rating_group
from {{ ref('int_claims_transactions_flagged') }}
where is_valid
