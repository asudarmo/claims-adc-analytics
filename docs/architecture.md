# Architecture

```
Python (synthetic claim generation)
   -> Postgres: raw + ground_truth schemas (landing zone + answer key)
      -> Great Expectations (ingestion validation, scored against ground_truth)
         -> dbt: staging -> intermediate (clean/quarantine) -> marts (star schema)
            -> Python reserving engine (LDF/CDF, Chain Ladder / Expected Claims / BF,
               credibility, extension scenario, reinsurance valuation) [next]
               -> Power BI (dashboard) [next]
```

Everything left of "[next]" is built and verified end to end against a live
Postgres instance. The reserving engine and dashboard are the current work.

## Why this split

**Postgres for storage.** A real, widely-recognised warehouse, free to run
locally via Docker, with a native Power BI connector, so no cloud account or
cost is needed to reproduce any of this.

**dbt owns ingestion cleaning and star-schema construction**, staging for
typing only, intermediate for the actual validation/cleaning rules using a
quarantine-not-drop pattern (see [validation.md](validation.md)), and marts
for the dimensions plus the fact tables everything downstream reads from.
This is also dbt's natural strength. A DAG of small, testable, documented
SQL models is a stronger audit trail than a monolithic script, and `dbt
build` running clean is a real correctness signal, not a self-report.

**The actuarial method chain, LDF/CDF, the three reserving bases,
credibility blending, the stress scenario, and reinsurance valuation, is a
standalone Python package, not dbt SQL.** This is a deliberate boundary, not
an accident of tooling. `dbt-postgres` doesn't support dbt's Python-model
feature at all (that needs a Snowflake/BigQuery/Databricks adapter), so "SQL
for everything" was never really a considered option once Postgres was
chosen. Keeping the actuarial logic in Python instead buys real things.

- **[chainladder](https://chainladder-python.readthedocs.io/)**, an
  established open-source package for exactly this kind of triangle-based
  reserving, is available to lean on for the core mechanics rather than
  reimplementing everything in SQL window functions.
- **Real unit tests.** An invariant like "a tail factor of 1.0 and a zero
  inflation shock must reproduce the base scenario exactly" is a natural
  `pytest` assertion, and the engine's outputs can be checked against
  figures from the original spreadsheet model as regression fixtures.
- The trade-off is that the audit trail becomes two artifacts, dbt's
  lineage graph for data prep and the Python package's own tests and docs
  for the actuarial half, instead of one. Considered acceptable, since it
  mirrors how a lot of real analytics-engineering-plus-data-science teams
  split "warehouse hygiene" from "the model" in practice.

**Power BI's DAX**, once built, is scoped to presentation over the engine's
precomputed results, plus one deliberate interactive piece, a what-if page
reimplementing just the stress-scenario formulas behind adjustable
parameters, so a viewer can move a slider and see the reserve respond live
without DAX having to carry the whole method chain.

## Validation is two layers, not one

A raw claims extract and a cleaned star schema fail in different ways, so
two different tools check them, at two different points.

- **Great Expectations**, against the `raw` Postgres schema right after
  load, does record-level and statistical checks such as nulls, referential
  integrity, regex validity, duplicate detection, and an outlier test.
- **dbt**, against the `intermediate`/`marts` layers, does structural and
  business-rule integrity checks on the *transformed* data, such as
  uniqueness, relationships, monotonic cumulative paid, and accepted ranges.

Full detail, including how well each approach actually performed when
scored against the known-issue answer key, is in
[validation.md](validation.md).
