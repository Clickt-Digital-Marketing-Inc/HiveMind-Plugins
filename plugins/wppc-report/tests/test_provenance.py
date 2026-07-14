"""Run-metadata block + k-honesty provenance (k_source, attrs, build_run_meta)."""

from wppc.model import build_run_meta
from wppc.score import estimate_k, score

from conftest import make_segments


def _row(results, seg):
    return results.loc[results["segment_id"] == seg].iloc[0]


def test_k_source_fallback_single_segment(example_weights):
    """A single-segment frame cannot estimate k -> provenance is 'fallback'."""
    df = make_segments([
        {"segment_id": "solo", "click": 100, "engagement": 60, "add_to_cart": 20,
         "initiate_checkout": 12, "purchase": 8, "repeats": 3},
    ])
    results = score(df, example_weights)
    assert results.attrs["k_source"] == "fallback"
    assert results.attrs["n_segments"] == 1


def test_k_source_estimated_multi_segment(example_weights):
    """Anchor + thin segments let method-of-moments succeed -> 'estimated'."""
    df = make_segments([
        {"segment_id": "anchor", "click": 5000, "engagement": 2500, "add_to_cart": 600,
         "initiate_checkout": 300, "purchase": 150, "repeats": 60},
        {"segment_id": "thin", "click": 8, "engagement": 7, "add_to_cart": 6,
         "initiate_checkout": 5, "purchase": 4, "repeats": 2},
    ])
    results = score(df, example_weights)
    assert results.attrs["k_source"] == "estimated"
    assert results.attrs["n_segments"] == 2
    # anchor (5000 clicks) is stabilized; thin (8 clicks) is not -> exactly 1.
    assert results.attrs["n_stabilized"] == 1
    assert _row(results, "anchor")["stabilized"] == "Y"
    assert _row(results, "thin")["stabilized"] == "N"


def test_estimate_k_provenance_tuple_and_bareness(example_weights):
    """return_provenance=True yields (k, method); default returns a bare float
    identical to the tuple's k."""
    from wppc.weights import FUNNEL_STATES

    df = make_segments([
        {"segment_id": "anchor", "click": 5000, "engagement": 2500, "add_to_cart": 600,
         "initiate_checkout": 300, "purchase": 150, "repeats": 60},
        {"segment_id": "thin", "click": 8, "engagement": 7, "add_to_cart": 6,
         "initiate_checkout": 5, "purchase": 4, "repeats": 2},
    ])
    clicks = df["clicks"].astype(float)
    w = example_weights.w
    numerator = sum(df[s].astype(float) * w[s] for s in FUNNEL_STATES)
    numerator = numerator + df["repeats"].astype(float) * w["repeat"]
    wppc = numerator / clicks
    baseline = float(numerator.sum()) / float(clicks.sum())

    bare = estimate_k(df, example_weights, wppc, clicks, baseline)
    k, method = estimate_k(df, example_weights, wppc, clicks, baseline, return_provenance=True)
    assert method == "estimated"
    assert isinstance(bare, float)
    assert bare == k


def test_build_run_meta_keys_and_stubs(example_weights):
    df = make_segments([
        {"segment_id": "anchor", "click": 5000, "engagement": 2500, "add_to_cart": 600,
         "initiate_checkout": 300, "purchase": 150, "repeats": 60},
        {"segment_id": "thin", "click": 8, "engagement": 7, "add_to_cart": 6,
         "initiate_checkout": 5, "purchase": 4, "repeats": 2},
    ])
    results = score(df, example_weights)
    meta = build_run_meta(results, example_weights, platform="google")

    expected_keys = {
        "baseline", "replacement", "k", "k_source", "n_segments", "n_stabilized",
        "self_check_pass", "telescope_sum", "generated", "platform",
        "weights_version", "drift", "decay", "incrementality",
    }
    assert set(meta.keys()) == expected_keys
    assert meta["k_source"] == "estimated"
    assert meta["platform"] == "google"
    assert meta["self_check_pass"] is True
    assert meta["n_segments"] == 2
    assert meta["n_stabilized"] == 1
    # The four stubs are None (filled by later issues).
    assert meta["weights_version"] is None
    assert meta["drift"] is None
    assert meta["decay"] is None
    assert meta["incrementality"] is None


def test_build_run_meta_generated_is_injectable(example_weights):
    """A passed ``generated`` is used verbatim (no clock read)."""
    df = make_segments([
        {"segment_id": "solo", "click": 100, "engagement": 60, "add_to_cart": 20,
         "initiate_checkout": 12, "purchase": 8, "repeats": 3},
    ])
    results = score(df, example_weights)
    pinned = "2020-01-01T00:00:00+00:00"
    meta = build_run_meta(results, example_weights, platform="meta", generated=pinned)
    assert meta["generated"] == pinned


def test_default_score_unchanged_locks_wppc(example_weights):
    """Default (no-arg) score() still yields the pinned worked-example wPPC."""
    df = make_segments([
        {"segment_id": "A", "click": 400, "engagement": 240, "add_to_cart": 60,
         "initiate_checkout": 28, "purchase": 10, "repeats": 2},
        {"segment_id": "B", "click": 400, "engagement": 120, "add_to_cart": 18,
         "initiate_checkout": 12, "purchase": 10, "repeats": 0},
    ])
    results = score(df, example_weights)
    assert round(float(_row(results, "A")["wPPC"]), 2) == 4.08
    assert round(float(_row(results, "B")["wPPC"]), 2) == 2.59
