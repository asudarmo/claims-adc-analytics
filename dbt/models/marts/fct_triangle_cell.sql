-- Grain: rating_group x accident_year x dev_age_months. The validated
-- cumulative-paid triangle - primary input to the standalone Python
-- reserving engine (see PLAN.md: the actuarial method chain lives there,
-- not in dbt).
--
-- Development age is evaluated at fixed calendar year-end diagonals
-- (12/31/2020 ... 12/31/2025), same convention as the original workbook
-- ("development age in months from the start of the accident year"):
-- accident year Y observed at the end of year Y+k is (k+1)*12 months
-- developed. This is NOT the same as "months since each individual claim's
-- own accident date" - claims within one accident year have accident dates
-- spread across the whole year, so a per-claim continuous clock would
-- smear payments across bucket boundaries instead of snapping to the
-- shared annual evaluation points every claim in that year is actually
-- judged against.
with valid_payments as (
    select t.transaction_date, t.amount, h.rating_group, h.accident_year
    from {{ ref('int_claims_transactions_valid') }} t
    join {{ ref('int_claims_header_clean') }} h on t.claim_id = h.claim_id
    where t.transaction_type = 'Payment'
),

diagonals as (
    select generate_series(2020, 2025) as diagonal_year
),

accident_years as (
    select distinct accident_year from valid_payments
),

cells as (
    select
        ay.accident_year,
        (d.diagonal_year - ay.accident_year + 1) * 12 as dev_age_months,
        make_date(d.diagonal_year, 12, 31) as diagonal_date
    from accident_years ay
    cross join diagonals d
    where d.diagonal_year >= ay.accident_year
      and (d.diagonal_year - ay.accident_year + 1) * 12 <= 72
),

cumulative as (
    select
        c.accident_year,
        c.dev_age_months,
        p.rating_group,
        sum(p.amount) as cumulative_paid
    from cells c
    join valid_payments p
        on p.accident_year = c.accident_year and p.transaction_date <= c.diagonal_date
    group by c.accident_year, c.dev_age_months, p.rating_group
)

select
    rating_group,
    accident_year,
    dev_age_months,
    cumulative_paid - coalesce(
        lag(cumulative_paid) over (partition by rating_group, accident_year order by dev_age_months),
        0
    ) as incremental_paid,
    cumulative_paid
from cumulative
order by rating_group, accident_year, dev_age_months
