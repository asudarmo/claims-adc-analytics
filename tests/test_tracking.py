from datetime import datetime, timezone

from engine.tracking import flatten_parameters, new_invocation_id, new_run_id


def test_new_run_id_is_readable_sortable_and_suffixed_by_trend_source():
    ts = datetime(2026, 3, 5, 14, 30, 7, tzinfo=timezone.utc)
    assert new_run_id("Assumed", ts) == "run_20260305_143007_assumed"
    assert new_run_id("Estimated", ts) == "run_20260305_143007_estimated"


def test_new_run_id_defaults_to_now():
    run_id = new_run_id("Assumed")
    assert run_id.startswith("run_")
    assert run_id.endswith("_assumed")


def test_new_invocation_id_has_its_own_readable_format():
    ts = datetime(2026, 3, 5, 14, 30, 7, tzinfo=timezone.utc)
    assert new_invocation_id(ts) == "inv_20260305_143007"


def test_flatten_parameters_covers_by_group_global_and_estimated():
    assumptions_by_group = {
        "A": {"plan_loss_ratio": 0.62, "ext_tail_factor": 1.012},
        "B": {"plan_loss_ratio": 0.70, "ext_tail_factor": 1.034},
    }
    assumptions_global = {"loss_trend": 0.055, "cred_full": 1082}
    estimated_trend = {"A": 0.101, "B": 0.072}

    rows = flatten_parameters(assumptions_by_group, assumptions_global, estimated_trend)
    by_key = {(r["parameter_name"], r["rating_group"]): r["value"] for r in rows}

    assert by_key[("plan_loss_ratio", "A")] == 0.62
    assert by_key[("ext_tail_factor", "B")] == 1.034
    assert by_key[("loss_trend", None)] == 0.055
    assert by_key[("cred_full", None)] == 1082
    assert by_key[("estimated_loss_trend", "A")] == 0.101
    assert by_key[("estimated_loss_trend", "B")] == 0.072
    # 2 groups x 2 by-group params + 2 global params + 2 estimated = 8
    assert len(rows) == 8
