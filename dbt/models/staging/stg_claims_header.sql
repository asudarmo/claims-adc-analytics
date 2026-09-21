select
    claim_id,
    rating_group,
    accident_year::int as accident_year,
    accident_date,
    report_date,
    close_date,
    status
from {{ source('raw', 'claims_header') }}
