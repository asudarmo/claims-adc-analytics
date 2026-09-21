# Postgres schema design

Five schemas, four layers, moving from "exactly what arrived, warts
included" to a queryable star schema.

## Layer 1, `raw`

Landing zone, loaded by `scripts/load_raw_to_postgres.py`. One table per
source CSV, column-for-column, with no constraints beyond structural ones
(see `db/init/01_raw_schema.sql` and
[`data/DATA_DICTIONARY.md`](../data/DATA_DICTIONARY.md) for the full column
reference). `claims_transactions.amount` is TEXT here specifically because
the extract contains non-numeric placeholders. That's not a typo, it's the
point. A landing zone that rejects or coerces malformed rows on the way in
isn't a landing zone, and validation needs something real left to catch.

## Layer 1b, `ground_truth`

The answer key, made up of `claims_header` (adds `true_ultimate`),
`claims_transactions` (uncensored, clean), and `injected_issues_log`. Never
read by the reserving engine or the dashboard, only by validation-recall
checks (see [validation.md](validation.md)) and later backtesting. See
`db/init/02_ground_truth_schema.sql`.

## Layer 2, `staging` (dbt, views)

One model per raw table, with a 1:1 grain and typing only, no business
rules yet.

| Model | Grain | Notes |
|---|---|---|
| `stg_claims_header` | 1 row / claim | pass-through, typed |
| `stg_claims_transactions` | 1 row / transaction | adds `amount_numeric` via a regex-guarded safe cast, keeping `amount_raw` alongside so a failed cast stays visible instead of silently disappearing |
| `stg_earned_premium` | 1 row / accident_year × rating_group | pass-through, typed |
| `stg_rate_changes` | 1 row / accident_year × rating_group | pass-through, typed |

## Layer 3, `intermediate` (dbt, views)

Where the cleaning rules actually live. Every cleaning model splits its
input into a **valid** stream that flows forward and a **quarantine**
stream that's kept, not discarded, with the reason attached. Nothing
silently disappears, and the quarantine tables can be diffed against
`ground_truth.injected_issues_log` to measure the rules' own recall and
precision instead of just asserting they work.

| Model | Purpose |
|---|---|
| `int_claims_header_clean` | missing `rating_group` is **not** imputed. It's relabelled `"Unclassified"` and kept out of group-level triangles, with the excluded volume disclosed rather than guessed away. Missing `report_date` **is** imputed, from the rating group's own median reporting lag. |
| `int_claims_transactions_flagged` → `_valid` / `_quarantine` | a referential check that the claim_id exists in the header, an amount that's castable and positive for a Payment, a transaction_date within `[report_date, valuation_date]`, and exact-duplicate detection on `(claim_id, transaction_date, transaction_type, amount_raw)` |
| `int_premium_rate_clean` | a `rate_change` outside a plausible ±25% band is treated as a magnitude keying error and divided by 100, the stated and documented correction rule rather than a silent guess. A missing premium cell is filled by the average of its neighbouring accident years for that rating group. |
| `int_claim_handler_assignment` | assigns each claim a Claims Handler from `dim_claims_handler`, restricted to that claim's own rating group, by a deterministic hash of claim_id rather than a random draw |

Statistical outlier detection for decimal-point errors, a payment keyed ×10
or ÷10, deliberately does **not** live here. See [validation.md](validation.md)
for why a distributional test struggles with this specific issue, and where
it's tried instead, Great Expectations, as an honestly-scored experiment
rather than a rule presented as reliable.

## Layer 4, `marts` (dbt, tables + seeds)

**Dimensions**

| Table | Key | Columns |
|---|---|---|
| `dim_rating_group` (seed) | rating_group | label, description |
| `dim_development_age` (seed) | dev_age_months | sequence_order (12/24/.../72) |
| `dim_accident_year` | accident_year | is_mature (≥72 months developed at the valuation date) |
| `dim_claims_handler` (seed) | handler_id | name, email, role (Claims Handler / Reserving Actuary / Senior Management), assigned_rating_group (nullable for the two oversight roles, who see every group rather than owning claims in one) |

**Facts**

| Table | Grain | Purpose |
|---|---|---|
| `fct_claim` | 1 row / claim | cumulative paid, latest case reserve, dev age at valuation, status, and `handler_id`, driving frequency, severity, closure-rate, and row-level-security-ready KPIs |
| `fct_claim_transactions` | 1 row / valid transaction | cleaned, and FK'd to claim, for drill-through detail |
| `fct_triangle_cell` | rating_group × accident_year × dev_age_months | the validated cumulative-paid triangle, the primary input to the reserving engine |
| `fct_premium_rate` | rating_group × accident_year | cleaned earned premium, corrected rate change, and a cumulative on-level rate index |
| `fct_data_quality_exceptions` | 1 row / flagged record | every quarantine, imputation, and correction from layer 3, unioned into one table in the same shape as `ground_truth.injected_issues_log` for direct comparison |

`fct_claim.handler_id` comes from `int_claim_handler_assignment` (layer 3):
each claim is assigned to a Claims Handler from its own rating group by a
deterministic hash of claim_id, not a random draw, so re-running dbt never
reshuffles who owns what. "Unclassified" claims (missing rating_group) get
no handler, same reasoning as everywhere else they're excluded.

Not yet built, queued for the retention work, is `dim_retention_policy`
(data_category, retention_years, rationale).

**Written by the Python reserving engine, not dbt:** `fct_reserve_results`
(run_id × rating_group × accident_year × method × scenario → ultimate,
reserve, loss ratio, and so on), `fct_reinsurance_valuation` (the Adverse
Development Cover valuation, run_id × scenario × booked_method, valued
once per candidate reserving basis rather than assuming
Bornhuetter-Ferguson is the only one a committee might book, see
[reserving-engine.md](reserving-engine.md) ("Booked reserve")),
`dim_reserving_run` (one
row per run: run_id, invocation_id, trend_source, run_timestamp, label,
is_promoted), and `fct_reserving_run_parameters` (every assumption used by
that run). `invocation_id` groups every run produced by one
`engine.main()` call together (one or two, depending on whether
`--trend-source` was `assumed`/`estimated` or `both`), while
`trend_source` records which loss-trend basis that particular run used.
Neither fact table carries a trend-source column itself, it's an
attribute of the run, not of each result row, so filtering to the
promoted run already fixes it. See [reserving-engine.md](reserving-engine.md)
("Assumed vs estimated loss trend") for the full reasoning. These four
tables are append-only run history rather than a warehouse layer built
from source data, so dbt only declares them as a source for structural
tests, it never builds them. See [reserving-engine.md](reserving-engine.md)
for why (a dbt table materialization would be dropped and recreated on
every `dbt run`, wiping that history).
See [architecture.md](architecture.md) for why the actuarial method chain
lives outside dbt.

## A correctness fix worth recording

`fct_triangle_cell`'s development age must be evaluated at fixed calendar
year-end diagonals relative to the accident year. 12 months means "observed
at the end of the accident year itself," 24 means "at the end of the next
year," and so on through 72. That's different from, and easy to confuse
with, "months since each individual claim's own accident date." Claims
within one accident year have accident dates spread across the whole
calendar year, so a per-claim continuous clock smears payments across
bucket boundaries instead of snapping every claim in that year to the same
shared evaluation points it's actually judged against. The first version of
this model used the per-claim clock and silently produced an empty
72-month cell for an otherwise fully-developed accident year, before this
was traced and fixed.
