"""wPPC scoring: worked example, shrinkage, k fallback, MAR, closing ratio."""

import logging

from wppc.score import K_FALLBACK, score

from conftest import make_segments


def _row(results, seg):
    return results.loc[results["segment_id"] == seg].iloc[0]


def test_worked_example_A_and_B(example_weights):
    """Two keywords, identical 2.5% CVR, different funnel quality.

    NOTE: the framework doc states wPPC_B = 2.89 (numerator 1,154.46), but that
    is an arithmetic error in the source — the listed counts telescope to
    1,035.30, i.e. wPPC_B = 2.59. The methodology is authoritative, so the
    fixture asserts the mathematically-correct 2.59. Keyword A (4.08) is correct
    in the source and reproduced exactly.
    """
    df = make_segments([
        {"segment_id": "A", "click": 400, "engagement": 240, "add_to_cart": 60,
         "initiate_checkout": 28, "purchase": 10, "repeats": 2},
        {"segment_id": "B", "click": 400, "engagement": 120, "add_to_cart": 18,
         "initiate_checkout": 12, "purchase": 10, "repeats": 0},
    ])
    results = score(df, example_weights)

    assert round(float(_row(results, "A")["wPPC"]), 2) == 4.08
    assert round(float(_row(results, "B")["wPPC"]), 2) == 2.59


def test_baseline_index_centers_on_100(example_weights):
    """wPPC+ is wPPC indexed to the clicks-weighted account baseline."""
    df = make_segments([
        {"segment_id": "A", "click": 400, "engagement": 240, "add_to_cart": 60,
         "initiate_checkout": 28, "purchase": 10, "repeats": 2},
        {"segment_id": "B", "click": 400, "engagement": 120, "add_to_cart": 18,
         "initiate_checkout": 12, "purchase": 10, "repeats": 0},
    ])
    results = score(df, example_weights)
    baseline = results.attrs["baseline"]
    # A is above the account average, B below.
    assert float(_row(results, "A")["wPPC+"]) > 100 > float(_row(results, "B")["wPPC+"])
    # Clicks-weighted mean wPPC equals the baseline (both have 400 clicks here).
    assert round((4.0803 + 2.5883) / 2, 2) == round(baseline, 2)


def test_shrinkage_pulls_thin_segment_toward_baseline(example_weights):
    """A thin, extreme segment is pulled toward the parent and flagged unstable."""
    df = make_segments([
        # Big, baseline-setting segment.
        {"segment_id": "anchor", "click": 5000, "engagement": 2500, "add_to_cart": 600,
         "initiate_checkout": 300, "purchase": 150, "repeats": 60},
        # Thin, very deep funnel — high raw wPPC, only a handful of clicks.
        {"segment_id": "thin", "click": 8, "engagement": 7, "add_to_cart": 6,
         "initiate_checkout": 5, "purchase": 4, "repeats": 2},
    ])
    results = score(df, example_weights)
    baseline = results.attrs["baseline"]
    k = results.attrs["k"]
    thin_clicks = 8

    thin = _row(results, "thin")
    obs = float(thin["wPPC"])
    shrunk = float(thin["wPPC_shrunk"])

    # Shrunk estimate lies strictly between observed and baseline, and closer to
    # baseline than the raw observation (empirical-Bayes pull).
    assert min(obs, baseline) < shrunk < max(obs, baseline)
    assert abs(shrunk - baseline) < abs(obs - baseline)
    # The stabilized flag is exactly clicks >= k; a handful of clicks is below k.
    assert thin_clicks < k
    assert thin["stabilized"] == "N"


def test_k_fallback_when_single_segment(example_weights, caplog):
    df = make_segments([
        {"segment_id": "solo", "click": 100, "engagement": 60, "add_to_cart": 20,
         "initiate_checkout": 12, "purchase": 8, "repeats": 3},
    ])
    with caplog.at_level(logging.INFO, logger="wppc"):
        results = score(df, example_weights)
    assert results.attrs["k"] == K_FALLBACK
    assert any("falling back to k" in r.message for r in caplog.records)
    # 100 clicks < 250 fallback -> not stabilized.
    assert _row(results, "solo")["stabilized"] == "N"


def test_mar_uses_replacement_and_sorts_desc(example_weights):
    df = make_segments([
        {"segment_id": "good", "click": 1000, "engagement": 700, "add_to_cart": 250,
         "initiate_checkout": 160, "purchase": 100, "repeats": 50},
        {"segment_id": "mid", "click": 1000, "engagement": 400, "add_to_cart": 90,
         "initiate_checkout": 50, "purchase": 25, "repeats": 8},
        {"segment_id": "poor", "click": 1000, "engagement": 150, "add_to_cart": 20,
         "initiate_checkout": 6, "purchase": 3, "repeats": 0},
    ])
    results = score(df, example_weights)
    # Sorted by MAR descending.
    assert list(results["MAR"]) == sorted(results["MAR"], reverse=True)
    # The strongest funnel tops the table.
    assert results.iloc[0]["segment_id"] == "good"


def test_closing_ratio_below_one_for_predictive_estimate(example_weights):
    """wPPC is an expected (xwOBA-style) estimate, so realized CM3/click < wPPC
    (closing ratio < 1) for a funnel-filling-but-not-closing segment."""
    df = make_segments([
        {"segment_id": "leaky", "click": 1000, "engagement": 800, "add_to_cart": 300,
         "initiate_checkout": 150, "purchase": 20, "repeats": 0},
        {"segment_id": "other", "click": 1000, "engagement": 400, "add_to_cart": 120,
         "initiate_checkout": 70, "purchase": 45, "repeats": 15},
    ])
    results = score(df, example_weights)
    assert float(_row(results, "leaky")["closing_ratio"]) < 1.0
