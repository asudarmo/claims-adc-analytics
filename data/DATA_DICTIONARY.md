# Data dictionary, synthetic claims data

Companion to [README.md](README.md), which explains the raw_extract vs
ground_truth split and lists the seeded data quality issues. This document
describes every column in every file. Row counts below are from the seed-42
run (`python scripts/generate_synthetic_claims.py`) and will change slightly
if the script is re-run with different parameters.

---

## data/raw_extract/claims_header_raw.csv
One row per claim known to exist as of the 31 Dec 2025 valuation date. **3,358 rows.**

| Column | Type | Nullable | Description | Example | Valid values |
|---|---|---|---|---|---|
| claim_id | string | No | Unique claim identifier. | `CLM-000001` | `CLM-######` |
| rating_group | string | **Yes** (seeded issue) | Rating group the policy was written under. Blank on about 0.2% of rows, logged as `missing_rating_group`. | `A` | `A`, `B`, `C`, or blank |
| accident_year | integer | No | Calendar year of the accident date. Reliable, not a target of the injected issues. | `2020` | 2020 to 2025 |
| accident_date | date (ISO) | No | Date of loss. | `2020-02-02` | within accident_year |
| report_date | date (ISO) | **Yes** (seeded issue) | Date the claim was first notified. Blank on about 0.4% of rows, logged as `missing_report_date`. | `2020-02-16` | on or after accident_date, on or before 2025-12-31 |
| close_date | date (ISO) | Yes (genuine) | Date of the claim's last payment or closure. Blank means still open at the valuation date. This is a real "unknown," not a data quality issue. | `2022-05-03` | on or after report_date, on or before 2025-12-31, or blank |
| status | string | No | `Open` or `Closed` as at 31 Dec 2025. A handful of `Closed` claims reopen later in the *ground truth*, but that reopening payment is dated after the valuation date, so it stays invisible here, exactly as a real extract would show it. | `Closed` | `Open`, `Closed` |

Note that `true_ultimate` is deliberately **not** present in this file.
That's the value the reserving model exists to estimate. It only exists in
`ground_truth/claims_header_ground_truth.csv`.

## data/raw_extract/claims_transactions_raw.csv
One row per claim movement, either a payment or a reserve snapshot. Joins to
claims_header_raw on `claim_id`. **19,817 rows**, including roughly 58
planted duplicate rows and 3 orphaned rows, described below.

| Column | Type | Nullable | Description | Example | Valid values |
|---|---|---|---|---|---|
| transaction_id | string | No | Unique transaction identifier. Duplicated rows get their own id, so this column alone won't catch duplicates. Compare (claim_id, transaction_date, transaction_type, amount) instead. | `TX-0000001` | `TX-#######` or `TX-DUP#####` |
| claim_id | string | No, but **not always valid** (seeded issue) | Claim the transaction belongs to. On 3 rows this has been mis-keyed to a claim_id that does not exist in claims_header_raw, logged as `orphan_claim_id`. | `CLM-000001` | should exist in claims_header_raw, though a few don't |
| transaction_date | date (ISO) | No, but **not always plausible** (seeded issue) | Date of the movement. On 3 rows this has been shifted past the valuation date, logged as `date_out_of_bounds`. | `2020-06-08` | expected between report_date and 2025-12-31 |
| transaction_type | string | No | `Payment` is the incremental amount paid at this date, so the sum of all Payment rows for a claim equals cumulative paid. `CaseReserveEstimate` is a point-in-time snapshot of the outstanding estimate, not incremental, so don't sum it across dates. | `Payment` | `Payment`, `CaseReserveEstimate` |
| amount | **mixed** string/numeric | No, but **not always numeric or valid** (seeded issues) | For Payment, the incremental amount, which should be greater than 0 since this account has no salvage or subrogation, so a negative payment is always an error and never a legitimate recovery. For CaseReserveEstimate, the outstanding reserve as of that date, which should be 0 or more. About 0.25% of rows have a decimal-point keying error (×10 or ÷10). About 0.3% contain the text `N/A`, `-`, or blank instead of a number. About 0.2% of Payment rows have an illegitimate negative sign. | `2465.65`, `N/A`, `-45.20` | numeric and non-negative expected. Text placeholders and negative Payment values are errors to catch, not to silently coerce. |

## data/raw_extract/earned_premium_raw.csv and rate_changes_raw.csv
Portfolio-level, one row per accident_year and rating_group. **18 rows each.**

| Column | Type | Nullable | Description | Example |
|---|---|---|---|---|
| accident_year | integer | No | | `2023` |
| rating_group | string | No | | `B` |
| earned_premium_000 | float | **Yes** (seeded issue, 1 cell) | Earned premium, GBP 000s. One cell is blank, logged as `missing_value` and mirroring "a period not written" from the original workbook. | `3,782.4` |
| rate_change | float | No, but **one value is a magnitude error** (seeded issue) | Average rate change achieved at renewal, as a decimal, so 0.05 means +5%. One row has been multiplied by 100, giving `4.5` instead of `0.045`, logged as `magnitude_error` and the same defect class as the "1.0 instead of 0.10" error in the original Table 3. | `0.045` |

---

## data/ground_truth/claims_header_ground_truth.csv
Same columns as claims_header_raw **plus `true_ultimate`**, and none of the
raw-extract quality issues. This is the true simulated position, uncensored.
**3,425 rows**, which includes claims not yet reported or closed as of the
valuation date, and is why the row count is higher than claims_header_raw.

| Extra column | Type | Description |
|---|---|---|
| true_ultimate | float | The claim's true total incurred cost once fully run off (GBP). This is the answer key for backtesting a reserve estimate. Never use it as a model input. |

## data/ground_truth/claims_transactions_ground_truth.csv
Same schema as claims_transactions_raw, but complete, including
transactions dated after 31 Dec 2025 (the "future" that the reserving
exercise is trying to predict), and clean, with no injected issues.
**About 26,700 rows** as of the current seed-42 run.

## data/ground_truth/injected_issues_log.csv
The answer key for the raw-extract data quality issues. Not derived from
the data. This is the actual list of what the generator broke, for checking
a validation rule's recall (does it catch everything logged here) and
precision (does it avoid flagging clean rows).

| Column | Type | Description |
|---|---|---|
| table | string | Which raw_extract file the issue was planted in, one of `claims_header`, `claims_transactions`, `earned_premium`, or `rate_changes`. |
| key | string | The claim_id, transaction_id, or accident_year-rating_group identifying the affected row. |
| issue_type | string | One of `missing_rating_group`, `missing_report_date`, `decimal_point_error`, `duplicate_transaction`, `text_placeholder`, `negative_payment`, `orphan_claim_id`, `date_out_of_bounds`, `magnitude_error`, or `missing_value`. |
| detail | string | A human-readable note of what changed, for example `amount 245.60 -> 2456.00 (x10)`. |

---

## Known limitations to keep in mind when validating

- `close_date` being blank is **not** in the issues log. It's a genuine
  right-censoring effect, since the claim is still open, not a data defect.
  Don't flag it as missing data.
- Duplicate rows in claims_transactions_raw keep distinct `transaction_id`
  values, so a naive `duplicated()` on the whole row will miss them if you
  include transaction_id in the comparison. Dedupe on
  `(claim_id, transaction_date, transaction_type, amount)` instead.
- `amount` must be read as a string or object column first and coerced with
  `pd.to_numeric(..., errors="coerce")`. Reading it as numeric directly in
  Power Query will error out on the placeholder rows rather than surfacing
  them as nulls to investigate.
