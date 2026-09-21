-- Grain: one row per claim. Drives frequency/severity/closure-rate KPIs.
with headers as (
    select * from {{ ref('int_claims_header_clean') }}
),

valid_txns as (
    select * from {{ ref('int_claims_transactions_valid') }}
),

paid_agg as (
    select claim_id, sum(amount) as cumulative_paid, count(*) as payment_count
    from valid_txns
    where transaction_type = 'Payment'
    group by claim_id
),

latest_reserve as (
    select distinct on (claim_id) claim_id, amount as latest_case_reserve
    from valid_txns
    where transaction_type = 'CaseReserveEstimate'
    order by claim_id, transaction_date desc
),

handler_assignment as (
    select * from {{ ref('int_claim_handler_assignment') }}
)

select
    h.claim_id,
    h.rating_group,
    h.rating_group_was_missing,
    h.accident_year,
    h.accident_date,
    h.report_date,
    h.report_date_was_imputed,
    h.close_date,
    h.status,
    coalesce(p.cumulative_paid, 0) as cumulative_paid,
    coalesce(p.payment_count, 0) as payment_count,
    coalesce(r.latest_case_reserve, 0) as latest_case_reserve,
    (extract(year from age(date '2025-12-31', h.accident_date)) * 12
        + extract(month from age(date '2025-12-31', h.accident_date)))::int as dev_age_months_at_valuation,
    ha.handler_id
from headers h
left join paid_agg p on h.claim_id = p.claim_id
left join latest_reserve r on h.claim_id = r.claim_id
left join handler_assignment ha on h.claim_id = ha.claim_id
