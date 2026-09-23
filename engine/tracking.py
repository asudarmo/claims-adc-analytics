"""
Run identity and parameter logging for the reserving engine, an
MLflow-style record of every recompute rather than each one silently
overwriting the last. See docs/reserving-engine.md ("Every run is tracked,
not overwritten") for the full design and why this is Python-owned rather
than a dbt model (a dbt table materialization would be dropped and
recreated on every dbt run, wiping the accumulated history).
"""
from datetime import datetime, timezone


def new_invocation_id(now: datetime | None = None) -> str:
    """One per call to engine.main(), regardless of how many runs that
    call produces (one, if a single trend source was chosen, or two, if
    "both" was). Lets the experiment explorer group runs that were
    triggered together without relying on timestamp equality."""
    now = now or datetime.now(timezone.utc)
    return f"inv_{now:%Y%m%d_%H%M%S}"


def new_run_id(trend_source: str, now: datetime | None = None) -> str:
    """A short, readable, sortable id - readable in a Power BI slicer,
    sortable by name, and unique enough for one engine invocation at a
    time (which is the only concurrency this needs to handle). Suffixed
    with the trend source so a "both" invocation's two runs get distinct
    ids sharing everything else."""
    now = now or datetime.now(timezone.utc)
    return f"run_{now:%Y%m%d_%H%M%S}_{trend_source.lower()}"


def flatten_parameters(assumptions_by_group: dict, assumptions_global: dict, estimated_trend: dict) -> list[dict]:
    """
    Every parameter that drove a run, as (parameter_name, rating_group,
    value) rows: the per-group assumptions, the global assumptions
    (including the *assumed* loss_trend), and the *estimated* loss_trend
    computed from that run's data, logged as its own named parameter so
    it's clear it's derived, not assumed.
    """
    rows = []
    for group, values in assumptions_by_group.items():
        for name, value in values.items():
            rows.append(dict(parameter_name=name, rating_group=group, value=float(value)))
    for name, value in assumptions_global.items():
        rows.append(dict(parameter_name=name, rating_group=None, value=float(value)))
    for group, value in estimated_trend.items():
        rows.append(dict(parameter_name="estimated_loss_trend", rating_group=group, value=float(value)))
    return rows
