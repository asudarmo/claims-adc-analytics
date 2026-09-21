-- Raw landing zone: mirrors data/raw_extract/*.csv column-for-column.
--
-- Deliberately loose: no primary keys, no foreign keys, no NOT NULL beyond
-- what is structurally guaranteed (an id column is always present as a
-- string, even when the row it points to doesn't exist). A landing zone's
-- job is to accept the extract exactly as it arrived, seeded data quality
-- issues included, and never reject or silently coerce a row on load.
-- Validation and cleaning happen downstream (Great Expectations, then dbt
-- staging models) — not here.
--
-- claims_transactions.amount is TEXT, not NUMERIC, because the raw extract
-- genuinely contains non-numeric placeholders ("N/A", "-", blank) in that
-- column by design (see data/DATA_DICTIONARY.md) — casting happens in
-- staging via to_numeric-style coercion, where failures can be flagged
-- rather than silently rejected at load time.

CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.claims_header (
    claim_id        TEXT,
    rating_group    TEXT,       -- nullable: seeded missing_rating_group issue
    accident_year   INTEGER,
    accident_date   DATE,
    report_date     DATE,       -- nullable: seeded missing_report_date issue
    close_date      DATE,       -- nullable: genuine (claim still open) — not a data issue
    status          TEXT,
    _loaded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    _source_file    TEXT
);

CREATE TABLE IF NOT EXISTS raw.claims_transactions (
    transaction_id      TEXT,
    claim_id             TEXT,   -- not FK-enforced: a handful deliberately reference no claim
    transaction_date     DATE,
    transaction_type     TEXT,
    amount               TEXT,   -- mixed numeric / text-placeholder, see note above
    _loaded_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    _source_file          TEXT
);

CREATE TABLE IF NOT EXISTS raw.earned_premium (
    accident_year        INTEGER,
    rating_group         TEXT,
    earned_premium_000   NUMERIC,   -- nullable: seeded missing_value issue
    _loaded_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    _source_file          TEXT
);

CREATE TABLE IF NOT EXISTS raw.rate_changes (
    accident_year   INTEGER,
    rating_group    TEXT,
    rate_change     NUMERIC,   -- seeded magnitude_error issue (e.g. 4.5 instead of 0.045), still numeric-typed
    _loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    _source_file     TEXT
);
