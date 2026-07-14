"""Monotonicity validation: later funnel stage must not exceed an earlier one."""

import logging

from wppc.score import _clamp_monotonic, score

from conftest import make_segments


def test_clamp_brings_later_stage_down_to_predecessor(caplog):
    df = make_segments([
        # add_to_cart (50) exceeds engagement (10) -> must clamp to 10.
        {"segment_id": "bad", "click": 100, "engagement": 10, "add_to_cart": 50,
         "initiate_checkout": 5, "purchase": 2, "repeats": 0},
    ])
    with caplog.at_level(logging.WARNING, logger="wppc"):
        clamped = _clamp_monotonic(df.copy())
    assert clamped.loc[0, "add_to_cart"] == 10
    assert any("Monotonicity violation" in r.message for r in caplog.records)


def test_clamp_cascades_down_funnel():
    df = make_segments([
        {"segment_id": "bad", "click": 100, "engagement": 10, "add_to_cart": 50,
         "initiate_checkout": 40, "purchase": 30, "repeats": 0},
    ])
    clamped = _clamp_monotonic(df.copy())
    # Each later stage clamped to its (already clamped) predecessor's floor.
    assert clamped.loc[0, "add_to_cart"] == 10
    assert clamped.loc[0, "initiate_checkout"] == 10
    assert clamped.loc[0, "purchase"] == 10


def test_score_runs_through_clamp_without_error(example_weights):
    df = make_segments([
        {"segment_id": "bad", "click": 100, "engagement": 10, "add_to_cart": 50,
         "initiate_checkout": 5, "purchase": 2, "repeats": 0},
        {"segment_id": "ok", "click": 200, "engagement": 120, "add_to_cart": 40,
         "initiate_checkout": 22, "purchase": 12, "repeats": 4},
    ])
    results = score(df, example_weights)
    assert len(results) == 2
