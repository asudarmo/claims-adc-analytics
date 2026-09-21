"""
Great Expectations suite for the `raw` schema in Postgres (the landing zone
loaded by load_raw_to_postgres.py). Runs a battery of checks designed to
mirror the data quality issues deliberately seeded by
generate_synthetic_claims.py, then scores each check's recall/precision
against `ground_truth.injected_issues_log` — the actual answer key for what
was broken and where.

This is deliberately not a black box: each check states which issue_type it
targets, and the recall/precision table at the end tells you honestly which
checks work and which don't, rather than asserting that validation "passed."

Usage: python scripts/gx_validate_raw.py
"""
import re
from pathlib import Path

import great_expectations as gx
import pandas as pd
from dotenv import load_dotenv
import os
from sqlalchemy import create_engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

VALUATION_DATE = "2025-12-31"
NUMERIC_RE = r"^-?\d+(\.\d+)?$"


def get_connection_string():
    user = os.environ.get("POSTGRES_USER", "reserving")
    password = os.environ.get("POSTGRES_PASSWORD", "reserving_dev_only")
    db = os.environ.get("POSTGRES_DB", "claims_reserving")
    port = os.environ.get("POSTGRES_PORT", "5432")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


conn_string = get_connection_string()
engine = create_engine(conn_string)
context = gx.get_context(mode="ephemeral")
datasource = context.data_sources.add_postgres("claims_reserving_raw", connection_string=conn_string)

# ---------------------------------------------------------------------------
# Assets: raw tables directly, plus named Postgres views (db/init/03_check_views.sql)
# for anything cross-table/derived. Views, not inline GX query assets: GX's
# unexpected_index_query feature (used below to get the full flagged-row set
# past its 20-row unexpected_index_list cap) substitutes an asset's defining
# SQL directly after "FROM", which only produces valid SQL for a bare
# table/view reference, not an inline subquery.
# ---------------------------------------------------------------------------
TABLE_ASSETS = {
    "claims_header": ("raw", "claims_header"),
    "earned_premium": ("checks", "earned_premium_keyed"),
    "rate_changes": ("checks", "rate_changes_keyed"),
    "claims_transactions": ("raw", "claims_transactions"),
    "transactions_with_header": ("checks", "transactions_with_header"),
    "payments_numeric": ("checks", "payments_numeric"),
    "date_violations": ("checks", "date_violations"),
    "duplicate_transaction_groups": ("checks", "duplicate_transaction_groups"),
    "payment_log_zscore": ("checks", "payment_log_zscore"),
}

assets = {}
for name, (schema_name, table_name) in TABLE_ASSETS.items():
    asset = datasource.add_table_asset(name=name, table_name=table_name, schema_name=schema_name)
    assets[name] = asset.add_batch_definition_whole_table(f"{name}_batch").get_batch()

RESULT_FORMAT = lambda key_col: {"result_format": "COMPLETE", "unexpected_index_column_names": [key_col]}

# ---------------------------------------------------------------------------
# Checks: (name, asset, expectation, issue_type it targets, key column)
# ---------------------------------------------------------------------------
checks = [
    ("claim_id_unique", "claims_header",
     gx.expectations.ExpectColumnValuesToBeUnique(column="claim_id"),
     None, "claim_id"),
    ("rating_group_not_null", "claims_header",
     gx.expectations.ExpectColumnValuesToNotBeNull(column="rating_group"),
     "missing_rating_group", "claim_id"),
    ("rating_group_valid_set", "claims_header",
     gx.expectations.ExpectColumnValuesToBeInSet(column="rating_group", value_set=["A", "B", "C"]),
     None, "claim_id"),
    ("report_date_not_null", "claims_header",
     gx.expectations.ExpectColumnValuesToNotBeNull(column="report_date"),
     "missing_report_date", "claim_id"),
    ("status_valid_set", "claims_header",
     gx.expectations.ExpectColumnValuesToBeInSet(column="status", value_set=["Open", "Closed"]),
     None, "claim_id"),

    ("earned_premium_not_null", "earned_premium",
     gx.expectations.ExpectColumnValuesToNotBeNull(column="earned_premium_000"),
     "missing_value", "key"),
    ("earned_premium_positive", "earned_premium",
     gx.expectations.ExpectColumnValuesToBeBetween(column="earned_premium_000", min_value=0, strict_min=True),
     None, "key"),

    ("rate_change_plausible_band", "rate_changes",
     gx.expectations.ExpectColumnValuesToBeBetween(column="rate_change", min_value=-0.25, max_value=0.25),
     "magnitude_error", "key"),

    ("transaction_type_valid_set", "claims_transactions",
     gx.expectations.ExpectColumnValuesToBeInSet(
         column="transaction_type", value_set=["Payment", "CaseReserveEstimate"]),
     None, "transaction_id"),
    ("amount_is_numeric", "claims_transactions",
     gx.expectations.ExpectColumnValuesToMatchRegex(column="amount", regex=NUMERIC_RE),
     "text_placeholder", "transaction_id"),

    ("no_orphan_claim_id", "transactions_with_header",
     gx.expectations.ExpectColumnValuesToNotBeNull(column="header_claim_id"),
     "orphan_claim_id", "transaction_id"),

    ("payment_amount_positive", "payments_numeric",
     gx.expectations.ExpectColumnValuesToBeBetween(column="amount_numeric", min_value=0, strict_min=True),
     "negative_payment", "transaction_id"),

    ("no_date_violations", "date_violations",
     gx.expectations.ExpectTableRowCountToEqual(value=0),
     "date_out_of_bounds", "transaction_id"),

    ("no_duplicate_transactions", "duplicate_transaction_groups",
     gx.expectations.ExpectTableRowCountToEqual(value=0),
     "duplicate_transaction", "transaction_ids"),

    ("payment_log_zscore_bounded", "payment_log_zscore",
     gx.expectations.ExpectColumnValuesToBeBetween(column="log_z", min_value=-4, max_value=4),
     "decimal_point_error", "transaction_id"),
]

rows = []
flagged_keys = {}  # check_name -> set of flagged keys (for recall/precision)

for name, asset_name, expectation, issue_type, key_col in checks:
    batch = assets[asset_name]
    result = batch.validate(expectation, result_format=RESULT_FORMAT(key_col))
    r = result["result"]
    unexpected_count = r.get("unexpected_count", r.get("observed_value") if "observed_value" in r else None)
    if isinstance(expectation, gx.expectations.ExpectTableRowCountToEqual):
        unexpected_count = r.get("observed_value", 0)
    rows.append(dict(
        check=name, table=asset_name, issue_type=issue_type or "-",
        success=result["success"], unexpected_count=unexpected_count,
    ))
    # unexpected_index_list is capped (20 rows) even with result_format
    # COMPLETE - use the unexpected_index_query GX also returns to fetch the
    # full set for scoring, rather than under-counting recall against a
    # truncated sample.
    keys = set()
    index_query = r.get("unexpected_index_query")
    if index_query:
        full = pd.read_sql(index_query, engine)
        for v in full[key_col]:
            if isinstance(v, list):
                keys.update(v)
            elif v is not None:
                keys.add(v)
    flagged_keys[name] = keys

# ExpectTableRowCountToEqual is a table-level expectation - it has no concept
# of unexpected_index_list (there's no "the offending row" for a row count),
# so the two checks built on it above never got real keys from the loop.
# Fetch those directly for scoring purposes; the GX expectation itself is
# still what gates pass/fail.
date_viol_keys = set(pd.read_sql("SELECT transaction_id FROM checks.date_violations", engine)["transaction_id"])
flagged_keys["no_date_violations"] = date_viol_keys

dup_df = pd.read_sql("SELECT transaction_ids FROM checks.duplicate_transaction_groups", engine)
flagged_keys["no_duplicate_transactions"] = {tid for group in dup_df["transaction_ids"] for tid in group}

summary = pd.DataFrame(rows)
pd.set_option("display.width", 140)
print("=" * 90)
print("VALIDATION RESULTS")
print("=" * 90)
print(summary.to_string(index=False))

# ---------------------------------------------------------------------------
# Score each targeted check against the answer key
# ---------------------------------------------------------------------------
truth = pd.read_sql("SELECT issue_type, key FROM ground_truth.injected_issues_log", engine)

print("\n" + "=" * 90)
print("RECALL / PRECISION vs ground_truth.injected_issues_log")
print("=" * 90)
score_rows = []
for name, asset_name, expectation, issue_type, key_col in checks:
    if issue_type is None:
        continue
    truth_keys = set(truth.loc[truth.issue_type == issue_type, "key"])
    flagged = flagged_keys[name]
    tp = len(flagged & truth_keys)
    recall = tp / len(truth_keys) if truth_keys else float("nan")
    precision = tp / len(flagged) if flagged else float("nan")
    score_rows.append(dict(
        check=name, issue_type=issue_type, true_count=len(truth_keys),
        flagged_count=len(flagged), true_positives=tp, recall=round(recall, 2), precision=round(precision, 2),
    ))
score_df = pd.DataFrame(score_rows)
print(score_df.to_string(index=False))

print("""
Note on payment_log_zscore_bounded (decimal_point_error): recall/precision
are expected to be poor here, deliberately left in rather than tuned away.
Individual payment increments are inherently heterogeneous (a claim's early
part-payments and late true-up payments differ hugely in size even with no
error at all), so a distributional z-score - by rating group or even
within-claim - cannot reliably separate a x10/x0.1 keying error from normal
variation at this transaction grain. This is a real limitation, not a bug:
catching it properly needs a stronger signal (e.g. comparing a payment
against the claim's own case-reserve trajectory at that date, or an
absolute plausibility bound tied to sum insured) than a raw amount
distribution provides. Flagged as a known gap for the dbt intermediate
layer rather than papered over.
""")
