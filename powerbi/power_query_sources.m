// Power Query M source definitions for the Claims Reserving Analytics
// Postgres marts schema.
//
// WHY THIS FILE EXISTS
// Power BI's Advanced Editor edits exactly one query at a time, so this
// file cannot be pasted in a single action. It's a saved, reproducible
// copy of every query's M code, organised as one block per query, so the
// whole data-source layer can be rebuilt from scratch (or reviewed, or
// diffed after a change) without depending on whatever was clicked in the
// GUI at the time. See docs/setup.md for where this fits in the overall
// pipeline.
//
// EACH TABLE QUERY USES PostgreSQL.Database(...)'s documented `Query`
// option (a plain SQL string) rather than the connector's schema/table
// navigation syntax. This was a deliberate choice, the exact field names
// used to index into that navigation table (e.g. whether it's
// Source{[Schema="marts",Item="dim_claim"]} or some other shape) aren't
// something that could be verified without a working Power BI Desktop
// install to test against, whereas every SQL string below has been run
// directly against the live database and confirmed to return rows.
//
// HOW TO USE
// 1. In Power BI Desktop: Home > Transform Data > New Source > Blank Query.
// 2. Open that new query's Advanced Editor (Home > Advanced Editor).
// 3. Paste the "PostgresMartsConnection" block below, rename the query to
//    exactly that name (right pane, Query Settings > Name), and in Query
//    Settings uncheck "Enable load" for it (right-click the query in the
//    queries list > Enable Load) since it's a helper, not a table to bring
//    into the model.
// 4. For each table you want, repeat steps 1-2 with a new blank query,
//    paste that table's block, and name the query exactly the same as the
//    table (e.g. "dim_rating_group") - Power BI uses the query name as the
//    table name in the semantic model.
// 5. Click Close & Apply. All tables should load with no further prompts
//    beyond the initial PostgreSQL connection credentials (username
//    "reserving", password from your local .env - see docs/setup.md).
//
// If you'd rather not paste 16 queries by hand: only the tables you
// actually plan to use in the report need to be created. Anything skipped
// now can always be added later by repeating step 4 for that one table.

// =============================================================
// QUERY NAME: PostgresMartsConnection
// (helper query - disable "Enable load" for this one)
// =============================================================
let
    PGServer = "localhost:5432",
    PGDatabase = "claims_reserving"
in
    [Server = PGServer, Database = PGDatabase]

// =============================================================
// Dimensions
// =============================================================

// QUERY NAME: dim_rating_group
let
    Conn = PostgresMartsConnection,
    Source = PostgreSQL.Database(Conn[Server], Conn[Database], [Query = "SELECT * FROM marts.dim_rating_group"])
in
    Source

// QUERY NAME: dim_development_age
let
    Conn = PostgresMartsConnection,
    Source = PostgreSQL.Database(Conn[Server], Conn[Database], [Query = "SELECT * FROM marts.dim_development_age"])
in
    Source

// QUERY NAME: dim_accident_year
let
    Conn = PostgresMartsConnection,
    Source = PostgreSQL.Database(Conn[Server], Conn[Database], [Query = "SELECT * FROM marts.dim_accident_year"])
in
    Source

// QUERY NAME: dim_claims_handler
let
    Conn = PostgresMartsConnection,
    Source = PostgreSQL.Database(Conn[Server], Conn[Database], [Query = "SELECT * FROM marts.dim_claims_handler"])
in
    Source

// QUERY NAME: dim_reserving_run
let
    Conn = PostgresMartsConnection,
    Source = PostgreSQL.Database(Conn[Server], Conn[Database], [Query = "SELECT * FROM marts.dim_reserving_run"])
in
    Source

// =============================================================
// Facts
// =============================================================

// QUERY NAME: fct_claim
let
    Conn = PostgresMartsConnection,
    Source = PostgreSQL.Database(Conn[Server], Conn[Database], [Query = "SELECT * FROM marts.fct_claim"])
in
    Source

// QUERY NAME: fct_claim_transactions
let
    Conn = PostgresMartsConnection,
    Source = PostgreSQL.Database(Conn[Server], Conn[Database], [Query = "SELECT * FROM marts.fct_claim_transactions"])
in
    Source

// QUERY NAME: fct_triangle_cell
let
    Conn = PostgresMartsConnection,
    Source = PostgreSQL.Database(Conn[Server], Conn[Database], [Query = "SELECT * FROM marts.fct_triangle_cell"])
in
    Source

// QUERY NAME: fct_premium_rate
let
    Conn = PostgresMartsConnection,
    Source = PostgreSQL.Database(Conn[Server], Conn[Database], [Query = "SELECT * FROM marts.fct_premium_rate"])
in
    Source

// QUERY NAME: fct_data_quality_exceptions
let
    Conn = PostgresMartsConnection,
    Source = PostgreSQL.Database(Conn[Server], Conn[Database], [Query = "SELECT * FROM marts.fct_data_quality_exceptions"])
in
    Source

// =============================================================
// Reserving engine output (Python-written, see docs/reserving-engine.md)
// =============================================================

// QUERY NAME: fct_reserve_results
let
    Conn = PostgresMartsConnection,
    Source = PostgreSQL.Database(Conn[Server], Conn[Database], [Query = "SELECT * FROM marts.fct_reserve_results"])
in
    Source

// QUERY NAME: fct_reinsurance_valuation
let
    Conn = PostgresMartsConnection,
    Source = PostgreSQL.Database(Conn[Server], Conn[Database], [Query = "SELECT * FROM marts.fct_reinsurance_valuation"])
in
    Source

// QUERY NAME: fct_reserving_run_parameters
let
    Conn = PostgresMartsConnection,
    Source = PostgreSQL.Database(Conn[Server], Conn[Database], [Query = "SELECT * FROM marts.fct_reserving_run_parameters"])
in
    Source

// =============================================================
// Assumptions (dbt seeds - see dbt/seeds/)
// =============================================================

// QUERY NAME: assumptions_by_group
let
    Conn = PostgresMartsConnection,
    Source = PostgreSQL.Database(Conn[Server], Conn[Database], [Query = "SELECT * FROM marts.assumptions_by_group"])
in
    Source

// QUERY NAME: assumptions_global
let
    Conn = PostgresMartsConnection,
    Source = PostgreSQL.Database(Conn[Server], Conn[Database], [Query = "SELECT * FROM marts.assumptions_global"])
in
    Source
