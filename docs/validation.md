# Validation

Two layers, deliberately not one. See [architecture.md](architecture.md)
for why a raw extract and a cleaned star schema need different kinds of
checks. Both are scored against the same answer key,
`ground_truth.injected_issues_log`, not just asserted to "pass," because a
validation rule that always reports success is indistinguishable from one
that isn't running at all.

## Layer one, Great Expectations, against `raw`

`scripts/gx_validate_raw.py` runs 15 checks (GX 1.23, the "Fluent" API),
covering uniqueness, referential integrity via a LEFT JOIN, regex-based
numeric validity, range and domain bounds, exact-duplicate detection, and a
rating-group-partitioned log-z-score aimed at decimal-point errors.
Cross-table and derived checks are backed by real Postgres views
(`db/init/03_check_views.sql`, schema `checks`) rather than inline GX query
assets. GX's `unexpected_index_query` feature substitutes an asset's
defining SQL directly after `FROM`, which only produces valid SQL for a
bare table or view reference, not an inline subquery, and a named view
sidesteps that entirely.

### Results

| Check | Issue type | Recall | Precision |
|---|---|---|---|
| rating_group_not_null | missing_rating_group | 1.00 | 1.00 |
| report_date_not_null | missing_report_date | 1.00 | 1.00 |
| earned_premium_not_null | missing_value | 1.00 | 1.00 |
| rate_change_plausible_band | magnitude_error | 1.00 | 1.00 |
| amount_is_numeric | text_placeholder | 1.00 | 1.00 |
| no_orphan_claim_id | orphan_claim_id | 1.00 | 1.00 |
| payment_amount_positive | negative_payment | 1.00 | 1.00 |
| no_date_violations | date_out_of_bounds | 1.00 | 1.00 |
| no_duplicate_transactions | duplicate_transaction | 1.00 | 0.50 |
| payment_log_zscore_bounded | decimal_point_error | 0.04 | 0.09 |

The duplicate check's 0.50 precision is correct behaviour, not a weakness.
It flags **both** rows of a duplicate pair, since from the data's
perspective either one could be "the real one," and recall is what matters
there, which is 1.00.

The decimal-point check is honestly weak, and left that way rather than
tuned to look better. Individual payment increments are inherently
heterogeneous, since a claim's early part-payments and its final true-up
payment can differ by an order of magnitude with nothing wrong at all. So a
distributional z-score, whether pooled by rating group or computed
within-claim, can't reliably separate a genuine ×10 keying error from
normal variation at this grain. Both were tried. A rating-group log-z-score
topped out around recall 0.14 and precision 0.04 across several thresholds.
Comparing each payment to its own claim's median did better on recall, up
to about 0.6, but collapsed precision further, to roughly 0.01 to 0.02,
since a claim's own early and late part-payments are often several times
apart in size with nothing wrong at all. Catching this properly would need
a stronger signal than the amount distribution alone, such as comparing a
payment against the claim's own case-reserve trajectory at that date, or an
absolute plausibility bound tied to sum insured. Both are flagged as
candidates for the dbt intermediate layer rather than solved here.

## Layer two, dbt, against `intermediate` and `marts`

The cleaning models in `dbt/models/intermediate/` (see
[schema-design.md](schema-design.md) for the full list) apply the rules
GX's structural checks were validating, this time as the actual
transformation logic, plus imputation for the fields designed to be
recoverable rather than merely flagged, `report_date`,
`earned_premium_000`, and `rate_change`.

Every cleaning model quarantines bad rows instead of dropping them, unioned
into `fct_data_quality_exceptions`. On the current dataset, 19,817 raw
transactions go in, 19,672 come out valid, and 145 are quarantined,
matching the seeded issue counts (59 non-numeric, 59 duplicate-group
members, 19 negative or zero payments, 3 orphans) almost exactly, plus one
small, explainable discrepancy worth recording.

There are really two different remediation strategies behind these nine
rules, not nine independent one-offs. `rating_group_missing`,
`report_date_imputed`, `earned_premium_missing`, and
`rate_change_magnitude_corrected` are **repaired and kept**, a defensible,
stated rule produces a real substitute value (a group's median reporting
lag, a neighbour-year premium average, dividing an out-of-range rate
change by 100) and the record stays fully usable in every downstream
calculation. The five `claims_transactions` rules
(`orphan_claim_id`, `non_numeric_amount`, `negative_or_zero_payment`,
`date_out_of_bounds`, `duplicate_transaction`) are **quarantined and
excluded**, there's no safe way to guess the right claim, date, or amount
for a single payment record, so the transaction is dropped from
`int_claims_transactions_valid` rather than fabricated, while still being
logged in full for disclosure. `fct_data_quality_exceptions.detail` states
which of the two happened for every row (leading with the action,
`relabelled`/`imputed`/`interpolated`/`corrected` for the first group,
`excluded, ...` plus the specific reason for the second), a real fix found
while actually building the Power BI data-quality page, the exclusion
rules originally all shared one generic `amount_raw=...` detail string
regardless of which rule fired, useless for `date_out_of_bounds` (which
isn't about the amount at all) and for `duplicate_transaction` (which
didn't say what it duplicated).

**Imputation can create a false positive in a downstream rule.** The
date-bounds check compares a transaction against its claim's `report_date`,
but for the 13 claims with a missing report_date, that value is itself
*imputed* from the rating group's median reporting lag, not the true one.
For one claim, the imputed date landed a single day after its real first
transaction, which then tripped the date-bounds rule twice even though
nothing was actually wrong. This is a genuine interaction between two
correct rules, not a bug in either, and it's left visible in the model's
comments rather than papered over with a grace-period fudge factor, since
that would just mask the same underlying imputation uncertainty rather than
resolve it.

## Bugs this exercise actually found

Building the scoring step, rather than just running checks and reading
"PASS," surfaced three real bugs in earlier work, all fixed.

1. **The loader was silently destroying part of the test data.** Pandas'
   default `na_values` handling treats `"N/A"` and blank fields as missing
   even with `dtype=str`, so two-thirds of the seeded `text_placeholder`
   issues were becoming `NULL` before they ever reached the `raw` schema.
   Fixed with `na_filter=False` on that one column.
2. **The orphan-claim-id generator's fallback could collide with a
   different real claim.** Its string-surgery approach to constructing a
   nonexistent id checked one candidate against real ids but not its own
   fallback branch, so twice, the "orphan" silently became a mis-pointed
   but *valid* reference instead. Replaced with an id offset well outside
   the real numbering range, with an explicit uniqueness assertion.
3. **A "+1 year" date shift doesn't guarantee landing out of bounds.**
   Shifting an early transaction's year forward by one can easily still
   fall inside the valid `[report_date, valuation_date]` window. Replaced
   with a fixed offset past the valuation date, which is guaranteed correct
   by construction rather than incidentally.

None of these would have been visible from "the checks ran and mostly
passed." They only showed up once actual recall was computed against the
answer key, which is the whole reason that scoring step exists.
