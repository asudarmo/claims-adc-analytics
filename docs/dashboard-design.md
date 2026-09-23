# Dashboard design: pages and charts

Ideation for the report layer, for you to build from in Power BI Desktop.
The visuals and page layout aren't built yet, this is still reference
material for that part, but the DAX measures listed under each page now
are built, living in `_measures.tmdl`. A suggested build order for the
visuals themselves is at the end if you want to prioritise.

## Design principles to carry across every page

- **One colour per rating group, used everywhere.** Pick three colours for
  A/B/C once and reuse them on every chart across every page, so a reader
  builds pattern recognition (e.g. "orange is always Group C") instead of
  re-learning a legend per page. Group C should probably read as the
  "attention" colour given it's consistently the more volatile group in
  this data.
- **Avoid pie/donut charts.** With three rating groups and three methods,
  a pie chart's imprecise area comparison doesn't add anything a bar chart
  doesn't already do better, and it doesn't scale if a fourth group is
  ever added.
- **State which run is being shown, on every page.** A small text card
  bound to the promoted run's `label` and `run_timestamp` (from
  `dim_reserving_run`) belongs somewhere consistent, like a header, so
  nobody mistakes which experiment produced the numbers on screen. Built,
  `Promoted Run Label` and `Promoted Run Timestamp`, both plain
  `CALCULATE(SELECTEDVALUE(...), dim_reserving_run[is_promoted] = TRUE)`,
  drop them on any page's header.
- **A consistent slicer panel** (rating group, accident year, at minimum)
  reused across pages via a shared visual/bookmark or just rebuilt
  identically, so filtering feels like one continuous tool rather than a
  set of disconnected pages.
- **Method/scenario need explicit, visible filters wherever
  `fct_reserve_results` is used**, never left to default aggregation. See
  `docs/dashboard.md` ("A design constraint to carry into the DAX
  measures"), summing across these columns blends different estimates of
  the same money together. Trend source no longer needs a separate filter
  here, it lives on `dim_reserving_run` and is already fixed once a page
  filters to the promoted run.
- **Always pull a row/column/slicer field from the shared dimension
  table, never from a fact table's own copy of that column.** Every
  fact-to-dimension relationship in this model is single-direction
  (filters flow from the dimension down to the fact table, not back up),
  so a field like `fct_triangle_cell[accident_year]` will correctly
  filter `fct_triangle_cell` itself but silently fails to reach any
  *other* fact table, like `fct_reserve_results`, that also relates to
  `dim_accident_year`. Caught this the hard way building Page 3's
  triangle matrices, `dim_accident_year[accident_year]` is the field that
  actually cascades to every fact table that needs it, the fact table's
  own column looks identical in the field list but doesn't. Same
  reasoning applies to `dim_rating_group[rating_group]` and
  `dim_development_age[dev_age_months]` (the latter, though, has no
  relationship to `fct_reserve_results` at all, so no dimension-table
  substitute fixes that one, ultimate genuinely doesn't vary by
  development age).

## Page 1: Reserve overview

**Purpose:** the headline page, what a reserving committee would look at
first. Shows the booked position only, no method/scenario comparison yet.

- KPI cards: Total Ultimate, Total Reserve, Ultimate Loss Ratio, Combined
  Ratio. Filtered to the promoted run, Base scenario, Bornhuetter-Ferguson
  method (the "booked" basis, see `docs/reserving-engine.md`). The
  promoted run's trend source comes along for free, no separate filter
  needed.
- Column chart: Reserve by Rating Group.
- Line or column chart: Ultimate Loss Ratio by Accident Year, one series
  per rating group.
- Slicers: rating group, accident year.
- **Measures built:** `Total Ultimate Booked`, `Total Reserve Booked`, each
  hard filtering `fct_reserve_results` to scenario = Base, method =
  BornhuetterFerguson, and `dim_reserving_run[is_promoted] = TRUE`.
  `Ultimate Loss Ratio Booked` and `Combined Ratio Booked` are recomputed
  from underlying totals (`DIVIDE([Total Ultimate Booked], [Total Earned
  Premium])`, and that plus a weighted expense ratio) rather than summing
  the row-level `loss_ratio`/`combined_ratio` columns directly, summing a
  ratio across rating groups would double-count incorrectly. Two small
  supporting measures back these: `Total Earned Premium` (not itself
  Booked-scoped, `fct_premium_rate` has no run_id/method/scenario at all)
  and `Total Expense Booked` (a `SUMX` over rating groups reconstructing
  each group's expense in currency terms from `assumptions_by_group[expense_ratio]`,
  since expense only exists there as a rate, not a dollar amount).

## Page 2: Reserving basis comparison (Chain Ladder / Expected Claims / BF)

**Purpose:** the core actuarial content, comparing the three bases and
using their spread as a reserving-uncertainty signal, the same idea
`fct_reserve_results` was built around.

- Clustered column chart: Ultimate by Method, grouped by Rating Group
  (Base scenario, promoted run).
- Table: Rating Group × Accident Year × Method → Ultimate, Reserve, with
  conditional formatting (e.g. a colour scale) to make divergence between
  methods visually obvious at a glance.
- Column or line chart: **method spread** (`MAX(ultimate) - MIN(ultimate)`
  across the three methods, per rating group × accident year) as its own
  chart, this is the single best visual for "how much does the choice of
  method matter here," and it's a genuinely interesting result already:
  Chain Ladder is visibly unstable for Group C's immature accident years
  (see `docs/reserving-engine.md`).
- **Measures built:** `Ultimate (Base, Promoted)` and `Reserve (Base,
  Promoted)`, the same Base-scenario, promoted-run filter as the Booked
  measures but without hard-filtering method, so method can sit on the
  chart axis instead. `Method Spread (Ultimate)` computes the MAX-MIN
  spread via `ADDCOLUMNS(VALUES(fct_reserve_results[method]), ...)` plus
  `MAXX`/`MINX`, evaluated fresh at whatever rating_group × accident_year
  context the visual is showing.
- **Built:** the clustered column chart uses `rating_group` as Legend
  alongside `method` on the axis, giving the "grouped by Rating Group"
  breakdown this page originally asked for (each method's three bars
  showing Group A/B/C side by side, rather than one account-level total
  per method). The Rating Group × Accident Year × Method comparison was
  built as three small-multiple line charts (one per rating group,
  `Ultimate (Base, Promoted)` and `Reserve (Base, Promoted)` by accident
  year and method within each) rather than a flat table, arguably clearer
  for spotting divergence between methods over time than a table would
  have been. The method spread chart confirms the finding it was built to
  surface directly, Group C's spread reaches 1.62M by 2025 against Group
  A's 0.36M.

## Page 3: Development and payout patterns

**Purpose:** the traditional actuarial triangle view, useful for anyone
checking the underlying data, not just the modelled output.

- Matrix visual: accident_year (rows) × dev_age_months (columns), from
  `fct_triangle_cell`, one matrix per rating group (a rating group slicer
  above one matrix, built this way rather than small multiples). **Use
  `dim_accident_year[accident_year]` for the row field, not
  `fct_triangle_cell[accident_year]`**, both look identical in the field
  list but the fact table's own copy won't cascade to `fct_reserve_results`
  if this matrix (or a later one) ever mixes in a measure from that table,
  see "Always pull a row/column/slicer field from the shared dimension
  table" above, this is the concrete case that caught it. **Built
  using `incremental_paid`, not `cumulative_paid` as originally specified
  here**, a real correction found while actually building it, summing
  `cumulative_paid` across development ages for the matrix's row/column
  totals produces a meaningless number (cumulative figures aren't
  additive across ages), while `incremental_paid` sums to something real,
  total paid to date per accident year, and per development age across
  all years. If a traditional cumulative view is still wanted later, it
  would need its own matrix without row/column totals, not a toggle on
  this one.
- Line chart: % of ultimate paid by development age, one line per rating
  group. Needs `cumulative_paid` divided by that rating group/accident
  year's ultimate, which means joining `fct_triangle_cell` to
  `fct_reserve_results` in a measure, worth checking this renders sensibly
  since the two tables aren't directly related in the model (no shared key
  beyond rating_group + accident_year, which do already both relate to the
  shared dimensions, so a measure using `RELATEDTABLE`-style logic through
  the dimensions should work, just flagging it's not a simple direct
  relationship).
- **Measures built:** `% of Ultimate Paid`. The first version divided
  `SUM(cumulative_paid)` by the whole book's ultimate
  (`CALCULATE([Ultimate (Base, Promoted)], REMOVEFILTERS(dim_development_age))`),
  and it was wrong, visible directly in the rendered chart, the curve rose
  then fell back down past dev age 40 instead of flattening out near 100%.
  The bug, at high development ages only the oldest accident years have
  actually reached that maturity, so `fct_triangle_cell` simply has no row
  for a young accident year at an age it hasn't reached yet. The numerator
  correctly shrinks to just the accident years present at that age, but
  the old denominator kept summing the *whole* book's ultimate regardless,
  so the ratio fell as the numerator's population shrank while the
  denominator didn't. Fixed by making the denominator track the same
  population as the numerator, row by row:
  ```
  % of Ultimate Paid =
  DIVIDE(
      SUM(fct_triangle_cell[cumulative_paid]),
      SUMX(
          fct_triangle_cell,
          CALCULATE([Ultimate (Base, Promoted)], REMOVEFILTERS(dim_development_age))
      )
  )
  ```
  The `SUMX` iterates only the `fct_triangle_cell` rows actually present
  in the current filter context, and `CALCULATE` inside it
  context-transitions each row into its own accident year before pulling
  that year's ultimate, so the denominator shrinks in step with the
  numerator instead of staying fixed at the whole book's total. Confirmed
  fixed, the chart is now monotonically increasing, flattening out near
  its asymptote as expected.

  Worth being precise about what this measure computes conceptually,
  since the DAX itself doesn't make it obvious, a filter context is
  invisible in the formula text, you have to know what visual it's sitting
  in to know what it sums. At a fixed `dev_age_months`, this sums a
  **column** of the triangle (same maturity, every accident year that's
  reached it), not a diagonal (same calendar/valuation date, which is what
  `engine/triangle.py`'s `latest_diagonal()` means, a different and
  already-used concept in this codebase). The two coincide only at the
  oldest development age, where exactly one accident year has reached it,
  a one-cell column and a one-cell diagonal happen to be the same thing.
  Age-to-age factors themselves are still not
  built, and remain optional, not currently in the data model as their
  own table, would need either a DAX measure recomputing them or a small
  new engine/dbt output if that gets fiddly in DAX, deliberately deferred
  in favour of Pages 6 and 8 for now.

## Page 4: Stress scenario and scenario explorer

**Purpose:** the base-vs-extension comparison the original coursework
asked for, plus the interactive what-if piece that was the whole reason
for keeping the extension formulas simple enough to reimplement in DAX.

- Clustered or waterfall chart: Reserve, Base vs Extension, by method.
- Table: same comparison broken out by rating group.
- **What-If parameters:** tail factor and inflation shock sliders, with
  measures reimplementing `engine/extension.py`'s formulas live in DAX
  over precomputed base-scenario inputs. This is the one page that
  deliberately duplicates engine logic into DAX for live interactivity,
  everywhere else should read `fct_reserve_results` directly rather than
  recompute anything.
- **Measures needed, still not built:** the tail/shock reimplementation (a
  non-trivial chunk of DAX, worth its own dedicated build session), plus
  whatever base-scenario inputs it needs exposed (CDF at latest diagonal,
  paid to date) that currently only exist inside the Python engine's
  internal `context` dict, not as their own table. This is the one page
  deliberately skipped while building out the rest of the measure set,
  writing DAX against data that doesn't exist yet as a table would just be
  guessing. Flagging this now: this page may need a small new marts table
  exposing those inputs, since DAX can't reach into the engine's internal
  Python state.

## Page 5: Reinsurance (Adverse Development Cover)

**Purpose:** directly answers the Board's two questions from the original
brief, what does the cover protect, and at what point does it stop.

- A **`booked_method` slicer** (ChainLadder / ExpectedClaims /
  BornhuetterFerguson), defaulted to BornhuetterFerguson, so the page opens
  on the same view it always has, but lets a viewer see how the whole
  cover's economics shift if the committee had booked a different basis.
  This is a required, visible filter, not optional, `fct_reinsurance_valuation`'s
  grain is now `run_id x scenario x booked_method`, leaving `booked_method`
  unfiltered would sum three different reserving bases' dollar figures
  together.
- KPI cards: Booked Reserve, Attachment, Exhaustion, Limit, Premium,
  Recovery, Net Benefit, from `fct_reinsurance_valuation` filtered to
  scenario = "Assumed stress" and whichever `booked_method` the slicer
  above has selected.
- A bullet-chart-style visual: booked reserve, attachment point,
  exhaustion point, and the stressed reserve all on one scale, so it's
  visually obvious whether the stress scenario is inside, at, or past
  exhaustion. Built showing **all three booked methods at once**, one row
  each, rather than the single method the `booked_method` slicer controls
  elsewhere on the page, comparing methods side by side turned out to be
  more useful here than drilling into one at a time, and the page had
  visible empty space to use well. See "Built" below for how.
- KPI card: Breakeven Inflation Rate, from the "Breakeven" scenario row
  (same `booked_method` selection), with a comparison against the assumed
  shock. Worth calling out explicitly in a text box or card subtitle: for
  a Bornhuetter-Ferguson booking, breakeven (3%) is *below* the assumed
  stress (4%), meaning the assumed stress scenario already exhausts the
  cover, a genuinely useful finding for the Board's actual question, not
  just a number to display. Chain Ladder's breakeven comes out even lower
  (2%), worth surfacing directly, since it means the choice of booking
  basis itself changes how exposed the cedant already is.
- **Measures built:** `Booked Reserve (ADC)`, `Attachment (ADC)`,
  `Exhaustion (ADC)`, `ADC Limit`, `Premium (ADC)`, `Stressed Reserve
  (Assumed Stress)`, `Recovery (Assumed Stress)`, `Net Benefit (Assumed
  Stress)`, all filtered to scenario = "Assumed stress" and the promoted
  run, and `Breakeven Inflation Rate` filtered to scenario = "Breakeven"
  instead. None of them filter `booked_method`, that's left to the page's
  slicer, exactly the direct pass-throughs this table was designed for, no
  new DAX logic beyond the standard promoted-run filter pattern.
- **Built**, and it's the one visual on this dashboard with no off-the-shelf
  equivalent, no native Power BI chart type or free AppSource visual draws
  "several labelled reference points against a measure bar, faceted by
  category," so this is a hand-written Deneb (Vega-Lite) spec, `booked`,
  `attachment`, `exhaustion`, `stressed`, and `booked_method` (renamed
  `method`) fed in as Values, `row`-faceted by `method` with a shared
  x-scale so all three are directly comparable.
  - **A real rendering bug caught from the first attempt**: bar marks
    without an explicit vertical position don't reliably centre and
    stack the way a mark's `height` property alone suggests they should,
    the first render showed three background bands and the stressed
    overlay bar as one smeared, indistinguishable block. Fixed by giving
    every bar layer an explicit pixel `y`/`y2` rather than relying on
    default anchoring, deterministic once specified, not something worth
    guessing at again.
  - **Two rounds of label placement fixes**: labels for `booked`,
    `attachment`, and `exhaustion` originally shared one vertical
    position and collided whenever two threshold values were close
    together (they usually are, attachment is only a few percent above
    booked reserve). Fixed by staggering each label and its dotted rule
    at a different fixed height, a staircase rather than a single row, so
    separation holds regardless of how close the underlying values are.
  - **Cross-highlighting from a Table instead of the page's slicer**,
    confirmed against Microsoft's own documentation before building it,
    a native Slicer visual can only ever drive a Filter interaction,
    never Highlight, that's a genuine Power BI platform restriction
    specific to slicers, not a Deneb limitation. A plain Table of
    `booked_method` can drive Highlight, so that's the interaction
    source, the slicer stays for the KPI cards (which need one method
    filtered), the table drives the bullet chart (which needs all three
    visible, just with one emphasised).
  - Deneb's **"Expose Cross-Highlight Values for Measures"** setting
    (Vega > Power BI Interactivity) adds `[measure]__highlight` and
    `[measure]__highlightStatus` companion fields per measure without
    disturbing the real values, essential, since without it Power BI's
    default highlight behaviour was substituting the underlying
    `booked`/`attachment`/`exhaustion`/`stressed` values themselves for
    non-highlighted rows, collapsing their bars to nothing rather than
    dimming them. In practice, `datum.stressed__highlight == null`
    (true exactly for rows excluded by an active highlight elsewhere)
    turned out simpler and more reliable than `__highlightStatus` for
    this spec.
  - **Opacity and colour split into two different jobs** after the first
    highlighting pass made the two non-selected methods too faded to
    read their own numbers against. Opacity now only dims the three
    background context bands; the stressed bar, the dotted rules, and
    every label stay at full opacity always, so all three methods' exact
    figures stay legible regardless of which one is selected. The
    selected method's stressed bar and its label switch to amber
    (`#B8860B`, chosen over red specifically to avoid an unintended
    "this one is bad" reading on an exhaustion chart) instead, so
    selection is communicated by colour, not by hiding the other two.
  - **A real bug from swapping the slicer for a Table**: switching
    `booked_method`'s selection mechanism from a single-select slicer to
    a Table (needed for cross-highlighting, see above) quietly removed
    the guarantee that exactly one method is always selected. A slicer
    in single-select mode with a default can never be "empty", a Table's
    resting state, before anyone clicks a row, has nothing selected at
    all, and in that state the nine ADC measures were summing all three
    booked methods' dollar figures together, precisely the failure mode
    this page's own design principle already named ("leaving
    `booked_method` unfiltered would sum three different reserving
    bases' dollar figures together"), it just needed the slicer's
    implicit guarantee removed to actually surface. Tried returning
    blank in that case first (`IF(HASONEVALUE(...), <calc>)` with no
    else), technically correct, but Power BI can't set a bookmark as a
    page's default view without a button or page-navigation trigger, so
    the page would always open showing `--` on every KPI card until a
    viewer clicked a row, a poor first impression for a page meant to be
    the headline reinsurance view. Settled on resolving the effective
    method once, in a `VAR`, falling back to `"BornhuetterFerguson"` (the
    same default the slicer used to guarantee) whenever the Table's
    selection isn't exactly one method, then filtering to that resolved
    value in a single `CALCULATE`, rather than branching into two
    near-duplicate `CALCULATE` blocks:
    ```
    VAR EffectiveMethod =
        IF(
            HASONEVALUE(fct_reinsurance_valuation[booked_method]),
            SELECTEDVALUE(fct_reinsurance_valuation[booked_method]),
            "BornhuetterFerguson"
        )
    RETURN
        CALCULATE(
            SUM(fct_reinsurance_valuation[booked_reserve]),
            FILTER(fct_reinsurance_valuation,
                fct_reinsurance_valuation[scenario] = "Assumed stress" &&
                fct_reinsurance_valuation[booked_method] = EffectiveMethod
            ),
            FILTER(dim_reserving_run, 'dim_reserving_run'[is_promoted] = TRUE)
        )
    ```
    Correctness no longer depends on any UI state at all, not a slicer
    default, not a bookmark, the page opens on BornhuetterFerguson every
    time and stays correct if a viewer deselects. One known, accepted
    edge case, `HASONEVALUE` is false both when nothing is selected and
    when more than one method is selected, so a hypothetical multi-select
    would also silently fall back to BornhuetterFerguson rather than
    showing a blended or blank result, not reachable with the Table's
    current single-select behaviour, not worth engineering around
    pre-emptively.

## Page 6: Data quality and validation

**Purpose:** shows the pipeline's own validation working, a good page for
demonstrating the analytics-engineering half of the project, not just the
actuarial output.

- Bar chart: count of exceptions by `rule_name`, from
  `fct_data_quality_exceptions`.
- Bar or matrix: exceptions by `source_table` × `rule_name`.
- KPI cards: counts for the headline categories (missing rating_group,
  imputed report_date, corrected rate changes).
- Optional stretch: the GX recall/precision table from
  `docs/validation.md` isn't currently in the data model (it's a
  script-run output, not a Postgres table), so it'd need a small new table
  if you want it on-screen rather than just referenced in the write-up.
- **Measures built:** `Exception Count` (a plain `COUNTROWS`), and the
  three headline categories, `Missing Rating Group Count`, `Imputed Report
  Date Count`, `Corrected Rate Change Count`, each filtering
  `fct_data_quality_exceptions[rule_name]` to its exact string
  (`rating_group_missing`, `report_date_imputed`,
  `rate_change_magnitude_corrected`, verified against
  `dbt/models/marts/fct_data_quality_exceptions.sql` rather than guessed).
  A fourth rule, `earned_premium_missing`, exists in the same table but
  wasn't asked for here, add a matching measure the same way if you want
  it on-screen too.

## Page 7: Experiment explorer

**Purpose:** demonstrates the run-tracking feature directly, lets a viewer
compare two recomputes side by side rather than only ever seeing the
promoted one.

- Table: `dim_reserving_run` (run_id, invocation_id, trend_source, label,
  run_timestamp, is_promoted), with the promoted row visually highlighted
  (conditional formatting).
- A slicer or pair of slicers to pick one or two run_ids to compare.
- Column chart: Reserve by run_id, method, for whichever run(s) are
  selected, trend_source is visible on the `dim_reserving_run` table
  above rather than needing its own axis here.
- Table: `fct_reserving_run_parameters` filtered to the selected run(s),
  so a viewer can see exactly what assumptions differed between two runs.
- **No measures needed, and none were built here.** `reserve`/`ultimate`
  already default to Sum on the raw `fct_reserve_results` columns, which
  is exactly right for this page, it's meant to browse arbitrary runs side
  by side, not just the promoted one, so a promoted-run-filtered measure
  like the ones built elsewhere would actively get in the way here. This
  page is mostly direct table browsing with slicers, a fine, low-effort
  page to build early if you want an easy win.

## Page 8 (stretch): Claims operations

**Purpose:** the page that would eventually carry the FCA Consumer Duty
KPIs and double as the Row-Level Security demo once `dim_claims_handler`
roles are wired up.

- KPI cards: claim count, average severity, closure rate, by rating group.
- A time-to-settle distribution (close_date minus report_date), e.g. a
  histogram or a box-and-whisker if you have that visual available.
- **Open-claim aging**: average age of open claims (valuation date minus
  report_date, filtered to `status = 'Open'`), plus an open-claims-by-age-
  bucket bar chart (e.g. 0-3, 3-6, 6-12, 12+ months). Fully computable from
  existing `fct_claim` columns, no schema change needed. Reopen rate was
  considered alongside this but ruled out, the synthetic generator's
  ground-truth reopens are deliberately dated after the 2025-12-31
  valuation cutoff (see `data/DATA_DICTIONARY.md`, the `status` column
  note), so they're invisible in this extract exactly as a real point-in-
  time snapshot would hide them, not a gap in what's built, a realistic
  limit on what this data can show.
- Table: claims per handler (`fct_claim.handler_id` → `dim_claims_handler`),
  a natural place to demo "View As Role" once RLS exists.
- **Measures built:** `Claim Count`, `Average Severity` (`DIVIDE(SUM(fct_claim[cumulative_paid]),
  [Claim Count])`), `Closed Claim Count`, `Closure Rate`, `Average Time to
  Settle (Days)` (`AVERAGEX` over closed claims,
  `DATEDIFF(report_date, close_date, DAY)`), `Average Age of Open Claims
  (Days)` (same idea, open claims against a shared `Valuation Date`
  measure instead of `close_date`), and four bucket measures for the aging
  chart, `Open Claims 0-3 Months`, `3-6 Months`, `6-12 Months`, `12+
  Months`. `Valuation Date` (`DATE(2025, 12, 31)`) is its own small
  measure so the cutoff lives in one place rather than five, worth
  knowing it duplicates `engine/main.py`'s `LATEST_YEAR = 2025` in a
  second place, Python and DAX don't share a constant, so if that ever
  changes both sides need updating by hand.

## Suggested build order, if prioritising

The DAX measures for Pages 1, 2, 3, 5, 6, 7, and 8 are all built now
(`_measures.tmdl`), so this order is really about visual layout in
Desktop, not DAX complexity anymore, except for Page 4, which still has no
measures at all.

1. **Page 1** (overview) and **Page 7** (experiment explorer), simplest
   visuals, and Page 7 shows off a feature (run tracking) nothing else in
   the report surfaces at all.
2. **Page 2** (method comparison) and **Page 5** (reinsurance), the core
   actuarial content.
3. **Page 6** (data quality), high narrative value for the
   analytics-engineering side of the project.
4. **Page 3** (triangles) and **Page 8** (claims ops), useful but more
   supporting detail than headline content.
5. **Page 4** (scenario explorer), last on purpose, it's the only page
   with no measures built yet, and still depends on a decision about
   whether a new marts table is needed to expose the engine's internal
   base-scenario inputs.
