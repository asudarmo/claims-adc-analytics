"""
Reads the dbt-built marts tables the engine needs, and writes its own
results back to Postgres. This is the one place the engine talks to the
warehouse; everything else in the package is pure functions over plain
Python values, which is what makes them easy to unit-test.
"""
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REAL_GROUPS = ("A", "B", "C")  # excludes the disclosed-but-unreserved "Unclassified" bucket


def get_engine():
    load_dotenv(PROJECT_ROOT / ".env")
    url = os.environ.get("DATABASE_URL")
    if not url:
        user = os.environ.get("POSTGRES_USER", "reserving")
        password = os.environ.get("POSTGRES_PASSWORD", "reserving_dev_only")
        db = os.environ.get("POSTGRES_DB", "claims_reserving")
        port = os.environ.get("POSTGRES_PORT", "5432")
        host = os.environ.get("POSTGRES_HOST", "localhost")
        url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    return create_engine(url)


def read_triangle(engine) -> pd.DataFrame:
    df = pd.read_sql("SELECT * FROM marts.fct_triangle_cell", engine)
    return df[df.rating_group.isin(REAL_GROUPS)].reset_index(drop=True)


def read_premium_rate(engine) -> pd.DataFrame:
    return pd.read_sql("SELECT * FROM marts.fct_premium_rate", engine)


def read_mature_claim_counts(engine, mature_years) -> dict:
    years = ", ".join(str(y) for y in mature_years)
    df = pd.read_sql(
        f"""
        SELECT rating_group, count(*) AS n
        FROM marts.fct_claim
        WHERE accident_year IN ({years}) AND rating_group IN ('A', 'B', 'C')
        GROUP BY rating_group
        """,
        engine,
    )
    return dict(zip(df.rating_group, df.n))


def read_claim_counts_by_year(engine, years) -> pd.DataFrame:
    """One row per rating_group x accident_year: how many claims are in
    fct_claim for that cell. Used by the severity trend estimator, which
    needs per-year counts rather than the credibility calculation's single
    total across the mature years."""
    years_list = ", ".join(str(y) for y in years)
    return pd.read_sql(
        f"""
        SELECT rating_group, accident_year, count(*) AS n
        FROM marts.fct_claim
        WHERE accident_year IN ({years_list}) AND rating_group IN ('A', 'B', 'C')
        GROUP BY rating_group, accident_year
        """,
        engine,
    )


def read_assumptions(engine) -> tuple[dict, dict]:
    by_group = pd.read_sql("SELECT * FROM marts.assumptions_by_group", engine).set_index("rating_group").to_dict("index")
    global_df = pd.read_sql("SELECT parameter, value FROM marts.assumptions_global", engine)
    glob = dict(zip(global_df.parameter, global_df.value))
    return by_group, glob


def write_table(engine, df: pd.DataFrame, table: str, schema: str = "marts"):
    """Drops and recreates a table from scratch. Only for tables where the
    latest run is the whole truth (nothing to accumulate)."""
    with engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS "{schema}"."{table}"'))
    df.to_sql(table, engine, schema=schema, if_exists="replace", index=False)
    print(f"  {schema}.{table:<28} {len(df):>4,} rows")


def append_table(engine, df: pd.DataFrame, table: str, schema: str = "marts"):
    """Adds rows to a table, creating it on the first call if it doesn't
    exist yet. Used for anything that accumulates run history rather than
    being replaced wholesale - pandas' to_sql creates the table
    automatically when it's missing regardless of if_exists, so this is
    safe to call before the table has ever been written."""
    df.to_sql(table, engine, schema=schema, if_exists="append", index=False)
    print(f"  {schema}.{table:<28} {len(df):>4,} rows appended")


def write_run_metadata(engine, run_id: str, invocation_id: str, trend_source: str, run_timestamp, label: str | None):
    df = pd.DataFrame([dict(
        run_id=run_id, invocation_id=invocation_id, trend_source=trend_source,
        run_timestamp=run_timestamp, label=label, is_promoted=False,
    )])
    append_table(engine, df, "dim_reserving_run")


def write_run_parameters(engine, run_id: str, parameter_rows: list[dict]):
    df = pd.DataFrame(parameter_rows)
    df.insert(0, "run_id", run_id)
    append_table(engine, df, "fct_reserving_run_parameters")
