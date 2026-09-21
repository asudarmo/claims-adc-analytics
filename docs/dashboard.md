# Power BI dashboard

`powerbi/Claims_Reserving_Models.pbip` is the Power BI Project (`.pbip` +
TMDL), the git-friendly format that makes it possible to edit the semantic
model as text rather than only through Power BI Desktop's UI. See
[architecture.md](architecture.md) and PLAN.md ("Power BI development
workflow") for why the split is: semantic model (tables, relationships,
DAX) as text, visual layout by hand in Desktop.

## Getting the marts tables in

Bootstrapped by connecting Desktop to Postgres and saving as a `.pbip`,
then every table's Power Query M was replaced with the versions in
[`powerbi/power_query_sources.m`](../powerbi/power_query_sources.m), one
`SELECT * FROM marts.<table>` per table through a shared connection query,
so the actual data-pulling logic is a reviewable, reproducible file rather
than whatever got clicked together in a dialog. See
[setup.md](setup.md#power-bi) for how to use it.

## Semantic model cleanup

Desktop's own auto-detection did a good job on the relationships that
matter most (all three `run_id` links between `dim_reserving_run` and the
engine's output tables, `rating_group` and `accident_year` to their
dimensions, `handler_id` to `dim_claims_handler`), but three things needed
fixing by hand before building anything on top of the model.

**One shared calendar, not five.** Auto Date/Time (on by default) had
created a separate hidden date table per date column, `dim_reserving_run.run_timestamp`,
and `fct_claim`'s `accident_date`/`report_date`/`close_date`, and
`fct_claim_transactions.transaction_date`, five in total. That's the
default, but it means you can't put one slicer on "Quarter" and have it
filter both claims and transactions consistently, since each date column
had its own isolated calendar. Replaced with a single `dim_date` table
(`CALENDARAUTO()`), disabled Auto Date/Time going forward
(`__PBI_TimeIntelligenceEnabled = 0`), and re-pointed the two dates that
matter most for analysis, `fct_claim.accident_date` (the claim cohort) and
`fct_claim_transactions.transaction_date` (payment timing), as **active**
relationships to it. `report_date` and `close_date` stay related but
**inactive**, since only one active relationship path is allowed between
any two tables, available to a specific DAX measure later via
`USERELATIONSHIP()` if reporting-lag or settlement-timing analysis needs
them. `run_timestamp` was left with no calendar relationship at all, it's
operational run metadata, not a claims-domain analysis axis.

**One spurious relationship removed.** Auto-detect had linked
`fct_reserving_run_parameters.parameter_name` to `assumptions_global.parameter`
purely because the text values happened to overlap. It only covers the
global parameters, not the by-group ones or the estimated trend, and would
have quietly misled anyone who found it into thinking it was a designed
join. Removed, and a genuinely useful one was added instead:
`fct_reserving_run_parameters.rating_group` → `dim_rating_group.rating_group`
(the ~half of rows logging a global parameter have a null rating_group and
simply won't match, which is correct).

**Wrong default aggregation on ratio and mixed-meaning columns.** Power
BI defaults every numeric column to `Sum`, which is wrong wherever the
column isn't actually additive: `loss_ratio`/`expense_ratio`/`combined_ratio`
on `fct_reserve_results`, `rate_change`/`cumulative_rate_index` on
`fct_premium_rate`, `plan_loss_ratio`/`ext_tail_factor`/`expense_ratio` on
`assumptions_by_group`, `cumulative_paid` on `fct_triangle_cell` (summing
across development ages would multiply-count the same claims), every
numeric column on `fct_reinsurance_valuation` (a table where even summing
across its own rows double-counts, `booked_reserve` repeats identically
across the Assumed-stress and Breakeven scenario rows for the same run),
and `value` on `fct_reserving_run_parameters` (which mixes loss_trend,
cred_full, and rate-on-line in one column, summing them together is
meaningless regardless of filter context). All switched to no default
summarization.

## A TMDL gotcha hit while making these edits

The first version of `relationships.tmdl` opened with a `//` comment block
explaining the date-relationship design, and Desktop refused to load the
project: `TMDL Format Error: Unexpected line type: Other! Document -
'./relationships' Line Number - 1`. Comments aren't valid as the leading
line of that document, at least not confirmed safe there, and rather than
guess at some other placement, every comment was stripped from
`relationships.tmdl` entirely and that explanation moved here instead,
where it was always going to be more durable anyway (a `.tmdl` comment
wouldn't survive Desktop rewriting the file on save, since Desktop doesn't
write comments back out itself). None of the other files had comments
added, so this was an isolated fix.

A second, more substantive error followed once the file parsed: `Table
'dim_date' must have ShowAsVariationsOnly property set to '1', because it
is a target of variation 'Variation' for column 'accident_date' ... when
variation notation is enabled.` The `variation`/`defaultHierarchy`
mechanism (what gives a date column its automatic Year/Quarter/Month
drill-down when dragged onto a visual) turns out to specifically require
its target table to be marked as variation-only, which is exactly the
`isHidden` + `showAsVariationsOnly` combination the original auto-generated
local date tables had and `dim_date` deliberately doesn't, since it's an
ordinary, visible, shared dimension, not a single-purpose hidden table. Carrying
the variation annotation over from the old per-column tables to the new
shared one was the mistake. Fixed by removing the `variation` blocks from
`fct_claim.accident_date` and `fct_claim_transactions.transaction_date`
entirely, the underlying relationships to `dim_date` are still there and
still do their job for filtering; the only thing lost is the automatic
hierarchy drill-down when a column is dragged onto a visual, which can be
had just as well by using `dim_date`'s own Year/Quarter/Month/Day columns
directly.

## A design constraint to carry into the DAX measures

`fct_reserve_results`' grain is rating_group × accident_year × method ×
scenario × run_id (trend source lives on `dim_reserving_run`, not as a
column here, see "Every run is tracked" in `docs/reserving-engine.md`).
Only rating_group and accident_year are safe to aggregate across. The
rest, method, scenario, run_id, are **alternative estimates of the same
money**, not independent slices: summing Chain Ladder's ultimate and
Bornhuetter-Ferguson's ultimate for the same cell isn't "more reserve,"
it's two different guesses at the same reserve added together.
`summarizeBy` can't fully guard against this (a viewer can still
explicitly choose Sum in a visual), so the real fix is in the measures
themselves: the first DAX measures written against this table should
establish a default that hard-filters to one scenario, one method, and
the promoted run (`dim_reserving_run[is_promoted] = TRUE`), with explicit
alternate measures for comparing methods or scenarios side by side,
rather than leaving `ultimate` to be dragged onto a visual unfiltered.
Filtering to the promoted run alone already fixes the trend source too,
that's the point of moving it onto `dim_reserving_run`, no separate
trend-source filter is needed downstream.

## The parameter_set to trend_source redesign

`fct_reserve_results` and `fct_reinsurance_valuation` used to carry a
`parameter_set` column ("Assumed" vs "Estimated"). The name was
misleading, it looked like "the full set of parameters used for this
row," but almost every parameter is already fixed by `run_id`, only the
severity trend's source varied. See
[reserving-engine.md](reserving-engine.md) ("Assumed vs estimated loss
trend") for the full reasoning. The fix moves `trend_source` onto
`dim_reserving_run` instead, alongside a new `invocation_id` column that
groups every run produced by one `engine.main()` call (one or two,
depending on the new `--trend-source assumed|estimated|both` CLI
choice). `parameter_set` is gone from both fact tables entirely.

This was applied by dropping and recreating all four engine-owned tables
(an accepted loss of the handful of test runs logged so far, not a
concern once the dashboard is actually in use) and rerunning the engine.
The TMDL edits were mechanical, add `invocation_id` and `trend_source` to
`dim_reserving_run.tmdl`, remove the `parameter_set` column block from
`fct_reserve_results.tmdl` and `fct_reinsurance_valuation.tmdl`.

The interesting part was `_measures.tmdl`, a file already sitting in
this project (added directly in Desktop) with one measure, `'Total
Ultimate Booked'`. Its filter had a `fct_reserve_results[parameter_set]
= "Assumed"` clause alongside `is_promoted = TRUE`. That clause is now
simply gone, not replaced with an equivalent `trend_source` filter,
because promoting a run already commits to a trend source under the new
design, so `is_promoted = TRUE` alone is enough to pin down the exact
row set. That's a direct, working confirmation of the design constraint
noted above, not just a claim about it.

## What's next

DAX measures over `fct_reserve_results` (starting with the constraint
above), then the What-If scenario-explorer page, then visual layout in
Desktop. See PLAN.md for the live list.
