# Setup & running

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python dependency management)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (local Postgres)

## One-time setup

```bash
uv sync                    # creates .venv, installs everything from pyproject.toml/uv.lock
cp .env.example .env       # local Postgres credentials, dev-only defaults
docker compose up -d       # starts Postgres 16, db/init/*.sql runs automatically on a fresh volume
```

## Running the pipeline

```bash
# 1. Generate the synthetic claims data (data/raw_extract/, data/ground_truth/)
uv run python scripts/generate_synthetic_claims.py

# 2. Load it into Postgres (raw + ground_truth schemas)
uv run python scripts/load_raw_to_postgres.py

# 3. Validate the raw extract (Great Expectations, scored against the answer key)
uv run python scripts/gx_validate_raw.py

# 4. Build the warehouse layer (staging -> intermediate -> marts)
cd dbt
DBT_PROFILES_DIR=. uv run --project .. dbt deps    # once, or after changing packages.yml
DBT_PROFILES_DIR=. uv run --project .. dbt build   # seeds + models + tests
cd ..

# 5. Run the reserving engine (reads fct_triangle_cell, writes fct_reserve_results
#    and fct_reinsurance_valuation back to Postgres)
uv run python -m engine.main

# 6. Run the engine's test suite
uv run pytest
```

A clean run of step 4 should end with every seed, model and test passing.
That's the actual correctness signal for this layer, not something to eyeball.
Step 6 should end with every test passing, including the invariant that a
tail factor of 1.0 and an inflation shock of 0 reproduce the base scenario
exactly (see [docs/reserving-engine.md](reserving-engine.md)).

## Sanity checks

```bash
# Rebuild a triangle from the simulated data and compare its shape against
# the original spreadsheet model's known figures
uv run python scripts/check_triangle_realism.py

# Inspect the warehouse directly
docker exec -it claims_reserving_postgres psql -U reserving -d claims_reserving
```

## Power BI

Not part of the pipeline steps above; a separate, manual step once you're
ready to build the dashboard.

`powerbi/power_query_sources.m` is a saved, reproducible copy of the Power
Query M code for every marts table, one query per table, each using
`PostgreSQL.Database`'s `Query` option with a plain `SELECT * FROM
marts.<table>` rather than the connector's schema-navigation syntax (every
one of those SQL strings has been run directly against the live database
and confirmed to return rows, so the risk that's actually being managed
here is a wrong or unverifiable M expression, not a wrong SQL string).
Paste each block into its own blank query's Advanced Editor in Power BI
Desktop, per the instructions at the top of the file, since the Advanced
Editor only edits one query at a time and this can't be a single paste.

## Starting over

`db/init/*.sql` only runs automatically against a **fresh** volume. To
rebuild the schema from scratch (e.g. after changing a `db/init/*.sql`
file):

```bash
docker compose down -v     # drops the Postgres volume, all loaded data goes with it
docker compose up -d
# then repeat steps 1-4 above
```

## Project layout

```
scripts/            synthetic data generation, Postgres loader, GX validation, triangle sanity-check
db/init/             Postgres DDL for the raw + ground_truth landing-zone schemas, run automatically by Docker Compose
dbt/                 staging -> intermediate -> marts (see docs/schema-design.md)
engine/              the standalone Python reserving engine (see docs/reserving-engine.md)
tests/               pytest suite for engine/
powerbi/             the .pbip project (semantic model + report), see docs/dashboard.md
data/                generated CSVs (raw_extract/, ground_truth/) + their data dictionary
docs/                this documentation
prototype/           the original spreadsheet-based model this project continues from
```
