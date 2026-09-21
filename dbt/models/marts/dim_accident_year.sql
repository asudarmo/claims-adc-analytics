select
    accident_year,
    (2025 - accident_year + 1) >= 6 as is_mature  -- >=72 months developed at the 31 Dec 2025 valuation date
from (
    select distinct accident_year from {{ ref('int_claims_header_clean') }}
) years
order by accident_year
