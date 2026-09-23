"""
Marks one reserving run as the officially promoted one, the run Power BI's
main dashboard reads by default. Exactly one run is promoted at a time.

This is deliberately its own small entry point rather than a flag on
engine.main: promoting is a fast, reviewed decision (flip a flag), not a
recompute, and keeping it separate means it can be wired into the same
Power Query "Run Python script" trigger as the recompute, just pointed at
this script instead, with the target run_id coming from a Power BI
parameter. See docs/reserving-engine.md ("Every run is tracked, not
overwritten").

Run: python -m engine.promote <run_id>
"""
import sys

from sqlalchemy import text

from engine import io


def promote(run_id: str):
    engine = io.get_engine()
    with engine.begin() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM marts.dim_reserving_run WHERE run_id = :run_id"), {"run_id": run_id}
        ).fetchone()
        if not exists:
            raise ValueError(f"No such run_id: {run_id}")
        conn.execute(text("UPDATE marts.dim_reserving_run SET is_promoted = false"))
        conn.execute(
            text("UPDATE marts.dim_reserving_run SET is_promoted = true WHERE run_id = :run_id"), {"run_id": run_id}
        )
    print(f"Promoted {run_id}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m engine.promote <run_id>")
        sys.exit(1)
    promote(sys.argv[1])
