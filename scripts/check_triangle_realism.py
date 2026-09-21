"""
Builds a proper cumulative-paid triangle from the simulated data (using the
observed, pre-dirty-injection view - i.e. what the raw extract would look
like after perfect cleaning) and checks it behaves like a real commercial
motor triangle: age-to-age factors > 1, decreasing towards 1, plausible
magnitude versus the original SMM092 Excel model.

Also quantifies how much the injected data issues distort the picture, by
comparing against the same triangle built from the actual raw_extract files.
"""
import numpy as np
import pandas as pd
from datetime import date

pd.set_option("display.width", 140)
pd.set_option("display.float_format", lambda x: f"{x:,.3f}")

VALUATION_DATE = date(2025, 12, 31)
DEV_AGES = [12, 24, 36, 48, 60, 72]


def months_between(d1, d2):
    return (d2.dt.year - d1.dt.year) * 12 + (d2.dt.month - d1.dt.month) - (d2.dt.day < d1.dt.day).astype(int)


def build_triangle(claims, txns):
    pay = txns[txns.transaction_type == "Payment"].merge(
        claims[["claim_id", "rating_group", "accident_year", "accident_date"]], on="claim_id"
    )
    pay["accident_date"] = pd.to_datetime(pay["accident_date"])
    pay["transaction_date"] = pd.to_datetime(pay["transaction_date"])
    pay["amount"] = pd.to_numeric(pay["amount"], errors="coerce")  # non-numeric -> NaN, dropped
    pay = pay.dropna(subset=["amount"])
    pay = pay[pay["amount"] > 0]  # a real cleaning step would investigate negatives, not silently drop

    dev_month = months_between(pay["accident_date"], pay["transaction_date"])
    pay["dev_age"] = np.ceil(dev_month.clip(lower=1) / 12) * 12
    pay = pay[pay["dev_age"].isin(DEV_AGES)]

    incr = pay.groupby(["rating_group", "accident_year", "dev_age"])["amount"].sum().unstack("dev_age")
    incr = incr.reindex(columns=DEV_AGES)
    cum = incr.cumsum(axis=1)
    return cum


def ldfs_from_triangle(cum):
    """Volume-weighted age-to-age factors, pooled across accident years, per group."""
    out = {}
    for group, sub in cum.groupby(level=0):
        sub = sub.droplevel(0)
        factors = {}
        for j in range(len(DEV_AGES) - 1):
            a, b = DEV_AGES[j], DEV_AGES[j + 1]
            both = sub[[a, b]].dropna()
            if len(both) == 0:
                factors[f"{a}-{b}"] = np.nan
            else:
                factors[f"{a}-{b}"] = both[b].sum() / both[a].sum()
        out[group] = factors
    return pd.DataFrame(out).T


# ---------------------------------------------------------------------------
# Clean / observed view (ground truth, censored at valuation date -
# equivalent to the raw extract IF it had no data quality issues)
# ---------------------------------------------------------------------------
gt_claims = pd.read_csv("data/ground_truth/claims_header_ground_truth.csv", parse_dates=["accident_date"])
gt_txns = pd.read_csv("data/ground_truth/claims_transactions_ground_truth.csv", parse_dates=["transaction_date"])

val_ts = pd.Timestamp(VALUATION_DATE)
obs_txns = gt_txns[gt_txns.transaction_date <= val_ts]
obs_claims = gt_claims.copy()

clean_triangle = build_triangle(obs_claims, obs_txns)
print("=" * 70)
print("CUMULATIVE PAID TRIANGLE - clean/observed simulated data (GBP)")
print("=" * 70)
print(clean_triangle.round(0))

print("\nImplied age-to-age (link) factors, clean data, volume-weighted:")
clean_ldfs = ldfs_from_triangle(clean_triangle)
print(clean_ldfs)

print("\nImplied CDF to 72 months (product of factors to the right), clean data:")
cdf = clean_ldfs.iloc[:, ::-1].cumprod(axis=1).iloc[:, ::-1]
cdf["CDF"] = cdf.prod(axis=1)
print(cdf[["CDF"]])

# ---------------------------------------------------------------------------
# Same triangle from the actual raw_extract files (uncleaned) for comparison
# ---------------------------------------------------------------------------
raw_claims = pd.read_csv("data/raw_extract/claims_header_raw.csv", parse_dates=["report_date"])
raw_claims["accident_date"] = pd.to_datetime(gt_claims.set_index("claim_id").loc[raw_claims.claim_id, "accident_date"].values)
raw_txns = pd.read_csv("data/raw_extract/claims_transactions_raw.csv", parse_dates=["transaction_date"])

raw_triangle = build_triangle(raw_claims, raw_txns)
print("\n" + "=" * 70)
print("CUMULATIVE PAID TRIANGLE - raw/uncleaned extract, naive numeric coercion (GBP)")
print("(non-numeric amounts dropped, negatives dropped, duplicates NOT removed)")
print("=" * 70)
print(raw_triangle.round(0))

diff = (raw_triangle - clean_triangle)
pct = (diff / clean_triangle * 100)
print("\nDifference vs clean (raw minus clean), % of clean cumulative paid:")
print(pct.round(2))

# ---------------------------------------------------------------------------
# Reference: LDFs implied by the ORIGINAL Excel workbook's Table 1 (2020 row,
# the only fully-developed accident year), for a sense-check of magnitude.
# ---------------------------------------------------------------------------
orig = {
    "A": [960.7, 1755.3, 2087.5, 2271.0, 2344.6, 2432.5],
    "B": [630.7, 1200.1, 1455.9, 1629.2, 1815.0, 1851.3],
    "C": [321.3, 686.5, 959.7, 1162.1, 1241.6, 1300.2],  # 24mo corrected for the planted typo (6865->686.5)
}
print("\nFor reference, age-to-age factors implied by the ORIGINAL Excel model's")
print("2020 accident year (Table 1, corrected), the only fully-developed row:")
for g, vals in orig.items():
    factors = [round(vals[i + 1] / vals[i], 3) for i in range(len(vals) - 1)]
    print(f"  Group {g}: {factors}   (12-24 through 60-72)")
