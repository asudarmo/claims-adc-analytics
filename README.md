# Claims Reserving Analytics

An end-to-end claims reserving analytics process for a commercial motor
account. It covers synthetic individual claims data, a validated warehouse,
an actuarial reserving engine, and a Power BI dashboard, spanning both the
analytics-engineering side (data generation, validation, modeling) and the
visual-analytics/dashboarding side of the problem.

**The problem:** a reserving exercise doesn't start from a tidy development
triangle. It starts from a raw, unreliable extract of individual claim
transactions that has to be validated, cleaned, and aggregated before any
actuarial method can run on it, and the result has to be presented so a
non-technical reader can see which basis is prudent and what's driving it.
This project builds that whole chain, with each stage checked rather than
assumed to work.

## Status

Data generation, validation, the warehouse layer, and the reserving engine
are built and verified end to end against a live Postgres instance. The
Power BI dashboard is in progress, see [docs/dashboard-design.md](docs/dashboard-design.md)
for what's built and what's left page by page.

## How it works

```
Python (synthetic claim generation)
   -> Postgres: raw + ground_truth schemas
      -> Great Expectations (ingestion validation, scored against ground truth)
         -> dbt: staging -> intermediate (clean/quarantine) -> marts (star schema)
            -> Python reserving engine (LDF/CDF, Chain Ladder / Expected Claims / BF,
               credibility, stress scenario, reinsurance valuation)
               -> Power BI dashboard [in progress]
```

Individual claim headers and transactions are simulated rather than
supplied as a pre-built triangle, and deliberately seeded with realistic
data quality issues. They're then validated two different ways, first
statistically at ingestion, then structurally after transformation, before
the development triangle and reserving results are built from what
survives. See [docs/architecture.md](docs/architecture.md) for the full
reasoning behind that split.

## Quick start

```bash
uv sync
cp .env.example .env
docker compose up -d
uv run python scripts/generate_synthetic_claims.py
uv run python scripts/load_raw_to_postgres.py
uv run python scripts/gx_validate_raw.py
cd dbt && DBT_PROFILES_DIR=. uv run --project .. dbt build && cd ..
uv run python -m engine.main
uv run pytest
```

Full detail, prerequisites, and how to reset are in
[docs/setup.md](docs/setup.md).

## Documentation

- [Architecture](docs/architecture.md), the pipeline end to end, and why the actuarial logic lives in Python rather than dbt SQL
- [Data generation](docs/data-generation.md), the simulation methodology, seeded data quality issues, and how its realism was checked against a known reference
- [Schema design](docs/schema-design.md), the Postgres layers from raw landing zone to star schema
- [Validation](docs/validation.md), the two-layer validation approach, scored recall/precision, and the bugs it actually found
- [Reserving engine](docs/reserving-engine.md), the actuarial method chain, where its assumptions live, and the judgment calls made explicit
- [Dashboard](docs/dashboard.md), the Power BI semantic model, the cleanup done on top of Desktop's defaults, and why
- [Dashboard design](docs/dashboard-design.md), page-by-page chart ideation for the report layer
- [Setup & running](docs/setup.md), prerequisites, environment, reproducing every step
- [Data dictionary](data/DATA_DICTIONARY.md), every generated column, its nullability, and which rows carry a seeded issue

## Project structure

```
scripts/            synthetic data generation, Postgres loader, GX validation, triangle sanity-check
db/init/             Postgres DDL for the raw + ground_truth landing-zone schemas
dbt/                 staging -> intermediate -> marts (dbt project)
engine/              the standalone Python reserving engine
tests/               pytest suite for engine/
powerbi/             the .pbip project (semantic model + report) and its Power Query M source
data/                generated CSVs (raw_extract/, ground_truth/) + data dictionary
docs/                detailed documentation (linked above)
prototype/           the original spreadsheet-based model this project continues from
```

## Acknowledgements

This project continues an earlier university coursework assignment that built
a commercial motor reserving model as a spreadsheet with an audit trail,
covering Chain Ladder, Expected Claims, Bornhuetter-Ferguson,
a credibility-weighted a priori loss ratio, a stress scenario,
and a reinsurance valuation. Those original materials are kept
under [prototype/](prototype/).

This is a substantial rebuild. The spreadsheet's pre-built
development triangle is replaced with individual claims data generated from
scratch and validated before aggregation, the whole pipeline runs on a real
data-warehouse stack (Postgres, dbt, Great Expectations) instead of a single
workbook, and the actuarial engine and dashboard are being rebuilt as a
tested, reproducible pipeline rather than spreadsheet formulas.
