-- amount_raw is kept alongside amount_numeric so a failed cast stays visible
-- (a null amount_numeric could mean "genuinely blank" or "text placeholder"
-- - amount_raw tells you which) rather than silently disappearing here.
select
    transaction_id,
    claim_id,
    transaction_date,
    transaction_type,
    amount as amount_raw,
    case when amount ~ '^-?\d+(\.\d+)?$' then amount::numeric else null end as amount_numeric
from {{ source('raw', 'claims_transactions') }}
