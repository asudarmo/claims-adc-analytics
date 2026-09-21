-- Ground truth: the answer key, not a pipeline input.
--
-- Loaded into its own schema so it is trivially easy to keep separate from
-- anything Power BI or the reserving engine reads from. Used for: checking
-- a Great Expectations suite's recall against injected_issues_log, and
-- later backtesting reserve estimates against true_ultimate.

CREATE SCHEMA IF NOT EXISTS ground_truth;

CREATE TABLE IF NOT EXISTS ground_truth.claims_header (
    claim_id        TEXT,
    rating_group    TEXT,
    accident_year   INTEGER,
    accident_date   DATE,
    report_date     DATE,
    true_ultimate   NUMERIC,   -- the answer a reserve estimate is trying to predict; never a model input
    close_date      DATE,
    status          TEXT,
    _loaded_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ground_truth.claims_transactions (
    transaction_id      TEXT,
    claim_id             TEXT,
    transaction_date     DATE,   -- includes dates after the valuation date, unlike the raw extract
    transaction_type     TEXT,
    amount               NUMERIC,   -- clean here: no injected issues in ground truth
    _loaded_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ground_truth.injected_issues_log (
    table_name   TEXT,   -- "table" in the source CSV; renamed to avoid the reserved word
    key          TEXT,
    issue_type   TEXT,
    detail       TEXT,
    _loaded_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
