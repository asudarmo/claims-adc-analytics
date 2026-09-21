-- One row per detected data quality issue, across every intermediate model
-- that flags one - the pipeline's own record of what it caught, in the same
-- shape as ground_truth.injected_issues_log so the two can be diffed
-- directly for a recall/precision check (see scripts/gx_validate_raw.py for
-- the same idea applied to the raw-extract layer).
select
    'claims_transactions' as source_table,
    transaction_id as key,
    rule_name,
    case rule_name
        when 'orphan_claim_id' then 'excluded, claim_id=' || claim_id || ' not found in claims_header'
        when 'non_numeric_amount' then 'excluded, amount_raw=' || coalesce(amount_raw, 'null') || ' is not numeric'
        when 'negative_or_zero_payment' then 'excluded, non-positive payment amount_raw=' || coalesce(amount_raw, 'null')
        when 'date_out_of_bounds' then 'excluded, transaction_date=' || transaction_date || ' is out of bounds'
        when 'duplicate_transaction' then 'excluded, duplicate of claim_id=' || claim_id ||
            ', transaction_date=' || transaction_date ||
            ', transaction_type=' || transaction_type ||
            ', amount_raw=' || coalesce(amount_raw, 'null')
    end as detail
from {{ ref('int_claims_transactions_quarantine') }}

union all

select
    'claims_header' as source_table,
    claim_id as key,
    'rating_group_missing' as rule_name,
    'relabelled Unclassified' as detail
from {{ ref('int_claims_header_clean') }}
where rating_group_was_missing

union all

select
    'claims_header' as source_table,
    claim_id as key,
    'report_date_imputed' as rule_name,
    'imputed report_date=' || report_date as detail
from {{ ref('int_claims_header_clean') }}
where report_date_was_imputed

union all

select
    'premium_rate' as source_table,
    accident_year || '-' || rating_group as key,
    'earned_premium_missing' as rule_name,
    'interpolated earned_premium_000=' || round(earned_premium_000, 1) as detail
from {{ ref('int_premium_rate_clean') }}
where earned_premium_was_missing

union all

select
    'premium_rate' as source_table,
    accident_year || '-' || rating_group as key,
    'rate_change_magnitude_corrected' as rule_name,
    'corrected rate_change=' || rate_change as detail
from {{ ref('int_premium_rate_clean') }}
where rate_change_was_corrected
