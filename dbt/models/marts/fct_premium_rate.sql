-- Grain: rating_group x accident_year. cumulative_rate_index is a plain
-- running product of (1 + rate_change), exposed as a convenience column;
-- deriving the on-level premium factor (ratio to the latest year) and
-- blending into an a priori loss ratio is the reserving engine's job, not
-- dbt's, see docs/architecture.md.
select
    accident_year,
    rating_group,
    earned_premium_000,
    earned_premium_was_missing,
    rate_change,
    rate_change_was_corrected,
    exp(sum(ln(1 + rate_change)) over (
        partition by rating_group order by accident_year
    )) as cumulative_rate_index
from {{ ref('int_premium_rate_clean') }}
