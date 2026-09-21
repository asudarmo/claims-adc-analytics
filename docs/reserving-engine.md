# Reserving engine

`engine/` is a standalone, pytest-tested Python package implementing the
full actuarial method chain. See [architecture.md](architecture.md) for why
this logic lives outside dbt. It reads `marts.fct_triangle_cell`,
`marts.fct_premium_rate`, and the assumption seeds from Postgres, and
writes `marts.fct_reserve_results` and `marts.fct_reinsurance_valuation`
back.

Run it with `uv run python -m engine.main [--trend-source assumed|estimated|both]
[--trend-value 0.06] [--label "a note"]`. Tests live in `tests/` and run
with `uv run pytest`.

## Every run is tracked, not overwritten

Each invocation is logged as its own run rather than replacing the
previous one, an MLflow-style history rather than a single mutable
"latest result." A run_id and timestamp are generated for each run
produced (`engine/tracking.py`), every assumption used (plus the
estimated trend, logged even on an assumed-trend run, for reference) is
logged to `marts.fct_reserving_run_parameters`, and results are appended
to `fct_reserve_results` / `fct_reinsurance_valuation` with that run_id
attached rather than dropping and recreating those tables.
`marts.dim_reserving_run` holds one row per run: `run_id`, `invocation_id`
(shared by every run one `engine.main()` call produces, one or two,
depending on `--trend-source`), `trend_source`, `run_timestamp`, an
optional `label`, and `is_promoted`.

These four tables are Python-owned, not dbt-built, on purpose: a dbt
table materialization is dropped and recreated on every `dbt run`, which
would silently wipe the accumulated history the next time anyone rebuilds
the warehouse. They're declared as a dbt source instead
(`dbt/models/marts/_reserving_engine_sources.yml`) purely so dbt can still
assert structural integrity on them (uniqueness of `run_id`, not-null
checks) without ever building them itself. A singular test
(`dbt/tests/at_most_one_promoted_run.sql`) checks that at most one run is
promoted at a time, "at most" rather than "exactly" since a fresh database
before anyone has promoted anything is a legitimate state, not a failure.

**Promoting** a run, marking it as the one Power BI's main dashboard
should read by default, is `engine/promote.py`, a small, separate entry
point (`python -m engine.promote <run_id>`) rather than a flag on
`engine.main`. Promoting is a fast, reviewed decision, flipping a flag,
not a recompute, and keeping it as its own script means it can be wired
into the same Power Query "Run Python script" trigger as the recompute
later, just pointed at this script instead, with the target run_id coming
from a Power BI parameter. DAX cannot do this itself under any
circumstance: it's a read-only calculation language with no write-back
capability to any data source at all.

## The method chain

For each rating group, per accident year.

1. **Development factors.** `engine/triangle.py` computes volume-weighted
   age-to-age factors (LDF) pooled across accident years, then chains them
   into cumulative development factors (CDF) back from 72 months.
2. **Chain Ladder.** `CL = paid_to_date x CDF`, the simplest basis, using
   only the claims themselves.
3. **On-level premium and the experience indication.** Earned premium is
   restated to the latest accident year's rate level using the cumulative
   rate index already computed in `fct_premium_rate`, and Chain Ladder
   ultimates for the three oldest (most fully developed) accident years are
   trended to the latest year's cost level and divided by that on-level
   premium, giving an experience-based indication of the ultimate loss
   ratio.
4. **Credibility blend.** That indication is blended with a business-plan
   loss ratio assumption, weighted by a limited-fluctuation credibility
   factor based on the group's claim count, giving the a priori loss ratio
   used by the next two methods.
5. **Expected Claims.** `EC = on_level_premium x a_priori_loss_ratio /
   trend`, using only premium and the a priori assumption, ignoring claims
   reported to date entirely.
6. **Bornhuetter-Ferguson.** `BF = paid_to_date + EC x (1 - 1/CDF)`,
   accepting the claims paid so far and applying the a priori expectation
   only to the undeveloped portion. This is what makes BF noticeably more
   stable than Chain Ladder for immature accident years, visible directly
   in the current results: 2025 (12 months developed) shows Chain Ladder
   loss ratios ranging up to 127% for the thinnest, longest-tailed rating
   group, while BF for the same cell sits at a much more plausible 81%.
7. **Stress scenario.** A tail factor extends every CDF beyond 72 months,
   the experience indication and a priori loss ratio are re-derived using
   the tail-adjusted Chain Ladder ultimates (since the tail changes what
   feeds the experience indication), and an inflation uplift is then
   applied to the unpaid portion of each tail-adjusted ultimate, scaled by
   how far in the future that payment is expected to fall rather than as a
   flat percentage. Setting the tail factor to 1.0 and the shock to 0 must
   reproduce the base scenario exactly, an invariant that has its own test
   (`tests/test_extension.py`).
8. **Reinsurance.** An Adverse Development Cover is valued at the account
   level (summed across every rating group and accident year, since the
   cover attaches to the whole account, not to any one group or year)
   against the stressed Bornhuetter-Ferguson reserve. The engine also
   solves for the breakeven inflation rate, the shock at which the cover's
   recovery reaches its limit, by bisection on the (monotonic) relationship
   between shock and stressed reserve.

## Assumed vs estimated loss trend

Some assumptions are inherently judgmental (a business-plan loss ratio) or
hypothetical by design (a stress inflation shock), but severity trend is
something the claims themselves can speak to directly. `engine/estimation.py`
fits a log-linear regression of average paid severity per claim, at a
maturity common to every mature accident year, against accident year, per
rating group.

Which trend to use is a genuine input choice, not something computed both
ways automatically every time. `python -m engine.main --trend-source`
takes `assumed` (the seeded judgmental value, or `--trend-value` to type a
specific number instead), `estimated`, or `both` (one run of each,
sharing an `invocation_id` so they're provably from the same underlying
data snapshot, but each still getting its own `run_id`). Whichever is
chosen, `trend_source` is recorded on `dim_reserving_run`, not as a column
on `fct_reserve_results` itself, since it's an attribute of the run, not
of each result row. This also means `dim_reserving_run[is_promoted]`
alone is enough to pin down the exact numbers being shown, no separate
trend-source filter needed downstream, promoting a run already commits to
which trend source it used.

Running it against the current data gives a real result worth being
upfront about: Group A and B's estimated trends (10.1% and 7.2%) are higher
than the assumed 5.5% but in a plausible range, while Group C's comes out
at 21.6%, driven by a jump in average severity per claim between the 2021
and 2022 mature-year cohorts. That's not a bug in the estimator, it's a
real property of a 3-point log-linear fit on a thin, heavy-tailed group.
Group C has by far the fewest claims per year and the heaviest large-loss
exposure of the three rating groups (see [data-generation.md](data-generation.md)),
so a single large claim landing in one cohort year materially moves that
year's average severity, and with only three mature years to fit against,
the regression has no way to distinguish "a real trend" from "one cohort
had a large loss." A more robust estimator (trimming large losses before
averaging, using more years even at a less mature common age, or a
frequency-severity split) would handle this better, but that's a
deliberate scope decision for later, not something to paper over now. The
An `estimated`-trend run should be read as "what the data says taken at
face value," not as a recommended booking basis for Group C as it stands.

## Where the assumptions live

Everything the formulas need but that isn't derived from the claims data
itself (the business-plan loss ratio, the credibility standard, the tail
factors, the inflation shock, the Adverse Development Cover's terms) is in
two dbt seeds, `dbt/seeds/assumptions_by_group.csv` and
`assumptions_global.csv`, loaded into `marts.assumptions_by_group` and
`marts.assumptions_global`. Keeping them there rather than hardcoded in the
engine means they're versioned, visible in `dbt docs`, and changeable
without touching Python.

## A judgment call worth being upfront about

The inflation uplift is meant to scale with how far in the future the
remaining unpaid amount for an accident year is expected to be paid, but
the original spreadsheet model's exact notation for that payment lag wasn't
available to carry forward. `engine/extension.py` defines it explicitly as
the time remaining to reach 72 months of development, plus the tail's own
average payment lag beyond that. A fully-developed accident year reduces to
just the tail lag, which is the one case the original assumption was
directly measuring, and a fresher accident year gets a longer lag, which is
the right qualitative shape. It's documented in the module itself as a
stated modelling choice, not a recovered formula.

## Booked reserve

The Adverse Development Cover's attachment and exhaustion points are set as
a percentage of the "booked" reserve, the base-scenario reserve for
whichever method a committee actually records in the accounts. Which
method that is isn't fixed in code, since deciding it is exactly the kind
of what-if question this dashboard is meant to support, so
`fct_reinsurance_valuation` values the cover once per candidate
`booked_method` (`ChainLadder`, `ExpectedClaims`, `BornhuetterFerguson`)
rather than assuming Bornhuetter-Ferguson is the only basis worth looking
at. `booked_reserve`, `attachment`, `exhaustion`, `adc_limit`, and
`premium` all move together with `booked_method`, since they're all
percentages or multiples of that one reference number, and
`stressed_reserve` tracks the same method too, so a row always compares a
method's stressed outcome against its own booked basis rather than mixing
methods. Grain is `run_id x scenario x booked_method`.

This generalizes something that was already true one axis over: the
severity-trend choice already moved the ADC economics (the assumed-trend
run's booked reserve differs from the estimated-trend run's), method is
simply the second input that legitimately varies the answer. Neither
`compute_scenario_ultimates` nor the tail/inflation-shock pipeline in
`engine/extension.py` needed to change to support this, they already
compute every method's post-stress ultimate on every call, method-specific
handling was only ever in the closure that picked one method's reserve
back out, so the fix is entirely inside `run_reserving_pass` in
`engine/main.py`.

## Test coverage

35 tests across seven files. The three worth knowing about specifically:

- `tests/test_triangle.py` checks the LDF and CDF arithmetic against Group
  A's 2020 accident year from the original spreadsheet model, a real
  external reference rather than a fixture invented for this project.
- `tests/test_extension.py` checks the tail=1.0/shock=0 invariant, both at
  the level of the individual extension functions and by reconstructing the
  base-scenario ultimates independently and comparing them to what the
  full extension pipeline produces under a no-op tail and shock.
- `tests/test_estimation.py` checks the severity-trend regression recovers
  a known constant growth rate exactly on a synthetic fixture, and that the
  common-maturity logic correctly picks the youngest mature year's own
  latest development age.
