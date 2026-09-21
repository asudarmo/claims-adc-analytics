-- Every row that failed at least one validation rule, kept (not dropped)
-- with the reason(s) disclosed. rule_name is the primary reason, by a fixed
-- priority order (documented below); rules_triggered lists everything that
-- fired, since a row can fail more than one check at once.
select
    transaction_id,
    claim_id,
    transaction_date,
    transaction_type,
    amount_raw,
    amount_numeric,
    case
        when is_orphan then 'orphan_claim_id'
        when is_non_numeric then 'non_numeric_amount'
        when is_negative_or_zero_payment then 'negative_or_zero_payment'
        when is_date_out_of_bounds then 'date_out_of_bounds'
        when is_duplicate then 'duplicate_transaction'
    end as rule_name,
    array_remove(array[
        case when is_orphan then 'orphan_claim_id' end,
        case when is_non_numeric then 'non_numeric_amount' end,
        case when is_negative_or_zero_payment then 'negative_or_zero_payment' end,
        case when is_date_out_of_bounds then 'date_out_of_bounds' end,
        case when is_duplicate then 'duplicate_transaction' end
    ], null) as rules_triggered
from {{ ref('int_claims_transactions_flagged') }}
where not is_valid
