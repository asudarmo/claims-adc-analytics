"""
Loads data/raw_extract/*.csv and data/ground_truth/*.csv into the Postgres
landing zone (schemas `raw` and `ground_truth`, created by db/init/*.sql).

This is intentionally a dumb loader: it does not validate, coerce, or drop
anything. Its only job is "what's in the CSV is what's in the table" — that
is what makes it a landing zone rather than a cleaning step. Great
Expectations and dbt staging models are where validation/coercion belong.

Usage: python scripts/load_raw_to_postgres.py
Reads connection settings from the environment (falling back to the same
defaults as docker-compose.yml / .env.example), or set DATABASE_URL directly.
"""
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
RAW_DIR = PROJECT_ROOT / "data" / "raw_extract"
GT_DIR = PROJECT_ROOT / "data" / "ground_truth"


def get_engine():
    url = os.environ.get("DATABASE_URL")
    if not url:
        user = os.environ.get("POSTGRES_USER", "reserving")
        password = os.environ.get("POSTGRES_PASSWORD", "reserving_dev_only")
        db = os.environ.get("POSTGRES_DB", "claims_reserving")
        port = os.environ.get("POSTGRES_PORT", "5432")
        host = os.environ.get("POSTGRES_HOST", "localhost")
        url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    return create_engine(url)


def load_table(engine, csv_path, schema, table, dtype=None, rename=None, na_filter=True):
    df = pd.read_csv(csv_path, dtype=dtype, na_filter=na_filter)
    if rename:
        df = df.rename(columns=rename)
    df["_source_file"] = csv_path.name if schema == "raw" else None
    if schema != "raw":
        df = df.drop(columns=["_source_file"])

    with engine.begin() as conn:
        conn.execute(text(f'TRUNCATE TABLE "{schema}"."{table}"'))
    df.to_sql(table, engine, schema=schema, if_exists="append", index=False)
    print(f"  {schema}.{table:<22} {len(df):>6,} rows  <- {csv_path.name}")


def main():
    engine = get_engine()
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version()")).scalar()
    print(f"Connected: {version.split(',')[0]}\n")

    print("Loading raw_extract/ -> raw schema:")
    load_table(
        engine, RAW_DIR / "claims_header_raw.csv", "raw", "claims_header",
    )
    load_table(
        engine, RAW_DIR / "claims_transactions_raw.csv", "raw", "claims_transactions",
        dtype={"amount": str}, na_filter=False,
        # na_filter=False is the actual fix here: pandas' default NA handling
        # treats "N/A" and "" as missing and silently turns them into NULL
        # even with dtype=str, which was quietly destroying two-thirds of the
        # seeded text_placeholder issues before they ever reached raw. Safe
        # to disable for this file specifically since every other column
        # (transaction_id/claim_id/transaction_date/transaction_type) is
        # always populated by construction.
    )
    load_table(engine, RAW_DIR / "earned_premium_raw.csv", "raw", "earned_premium")
    load_table(engine, RAW_DIR / "rate_changes_raw.csv", "raw", "rate_changes")

    print("\nLoading ground_truth/ -> ground_truth schema:")
    load_table(
        engine, GT_DIR / "claims_header_ground_truth.csv", "ground_truth", "claims_header",
    )
    load_table(
        engine, GT_DIR / "claims_transactions_ground_truth.csv", "ground_truth", "claims_transactions",
    )
    load_table(
        engine, GT_DIR / "injected_issues_log.csv", "ground_truth", "injected_issues_log",
        rename={"table": "table_name"},
    )

    print("\nDone.")


if __name__ == "__main__":
    main()
