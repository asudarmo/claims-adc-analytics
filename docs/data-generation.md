# Synthetic data generation

`scripts/generate_synthetic_claims.py` (seed 42) simulates individual claim
headers and transactions for a commercial motor account, rather than
starting from a pre-built development triangle. That's closer to what a
real reserving exercise actually receives, and it's what lets the rest of
this project have a validation layer, a star schema, and claim-level KPIs
at all.

## Scenario

Three rating groups, carried over from an earlier spreadsheet-based
reserving exercise this project continues.

| Group | Profile |
|---|---|
| A | Light commercial vehicles, largest claim count, fastest settlement, lowest average severity |
| B | Heavy goods vehicles, intermediate on all three dimensions |
| C | Specialist haulage, smallest claim count, highest average severity, longest settlement tail (a higher share of bodily injury claims) |

Six accident years (2020 to 2025), valuation date 31 Dec 2025.

## Simulation method

Per rating group and accident year.

1. **Frequency.** A fixed claim count per group and year, anchored to the
   same order of magnitude as the original workbook, with each claim
   assigned a random accident date within the year.
2. **Severity.** Lognormal, with a per-group mean and CV and a 5.5% p.a.
   severity trend applied to the mean. A small, group-specific probability
   of a large-loss multiplier, highest for Group C, adds a heavier tail
   without needing a full frequency-severity mixture model.
3. **Reporting delay.** Lognormal and short, days to a couple of months.
   This is deliberately not the source of long-tail behaviour, since in
   reality a motor claim is normally *reported* quickly even when it takes
   years to *settle*.
4. **Payment timing.** A Weibull-shaped cumulative payout curve per group
   (fast for A, long-tailed for C) turns each claim's total severity into a
   sequence of 2 to 8 partial payment transactions, with a case-reserve
   snapshot alongside each payment. That snapshot is a noisy estimate of
   the remaining outstanding, so some claims run over- or under-reserved.
5. **Reopens.** A small, group-specific probability of a further loss
   emerging after a claim has closed.
6. **Censoring at the valuation date.** This is what turns the simulation
   into a reserving problem rather than a fully-known dataset, since
   anything dated after 31 Dec 2025 is stripped from the "observed"
   extract. The uncensored version is kept as ground truth for later
   backtesting.

## Seeded data quality issues

Deliberately injected into `raw_extract/` only, never into `ground_truth/`.
The list covers missing rating_group, missing report_date, decimal-point
keying errors (×10/÷10) on payments, duplicate transaction rows, text
placeholders (`N/A`, `-`, blank) in the amount field, illegitimate negative
payments (this account has no salvage or subrogation, so a negative payment
is never legitimate), orphaned transactions referencing a claim_id that
doesn't exist, out-of-bounds transaction dates, a rate-change magnitude
error, and one missing premium cell. Every issue is logged in
`ground_truth/injected_issues_log.csv`, the answer key used to score the
validation layer (see [validation.md](validation.md)).

## Checking the result is realistic, not just plausible-looking

`scripts/check_triangle_realism.py` rebuilds a cumulative-paid triangle from
the simulated data and compares its age-to-age (link) factors against the
original workbook's one fully-developed accident year.

| | 12–24mo | 24–36mo | 36–48mo | 48–60mo | 60–72mo | CDF to 72mo |
|---|---|---|---|---|---|---|
| Original, Group A | 1.827 | 1.189 | 1.088 | 1.032 | 1.037 | 2.53 |
| Simulated, Group A | 1.601 | 1.090 | 1.012 | 1.003 | n/a | 1.99 |
| Original, Group B | 1.903 | 1.213 | 1.119 | 1.114 | 1.020 | 2.94 |
| Simulated, Group B | 1.765 | 1.186 | 1.052 | 1.029 | 1.004 | 3.32 |
| Original, Group C | 2.137 | 1.398 | 1.211 | 1.068 | 1.047 | 4.05 |
| Simulated, Group C | 1.810 | 1.195 | 1.106 | 1.072 | 1.023 | 5.16 |

It's not identical, since this is an independent simulation and not a
replay, but the shape is right. Factors decrease monotonically toward 1.0,
and the relative ordering (C slowest and heaviest-tailed, A fastest) holds
throughout.

The first pass didn't look like this. Group C's large-loss parameters
produced a CDF around 7.9x with a non-monotonic dip in the middle of the
curve, an unrealistic tail driven by too much large-loss weight relative to
the group's thin claim volume. That was caught by running this comparison,
then diagnosed and fixed by reducing the large-loss frequency and severity
multiplier before treating the dataset as usable for anything downstream.

The same script also compares a triangle built from the actual (dirty)
`raw_extract` files against one built from the clean ground truth, to
quantify how much the seeded errors distort a real cell. One decimal-point
miskey alone moved a triangle cell by roughly 10%, which is the kind of
number that makes a "why does validation matter" case concrete rather than
hypothetical.
