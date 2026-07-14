"""W1 weight-drift detection: snapshot sidecar + baseline compare + tolerance.

The snapshot captures the weight-table *inputs*; ``compare_weights_snapshot``
flags components whose relative change exceeds a tolerance that is passed in as
data (never a literal in the scoring kernels). The CLI writes the sidecar on
every run and, when pointed at a prior baseline, warns on drift without failing.
"""

import copy
import json
from pathlib import Path

from click.testing import CliRunner

from wppc.cli import DEFAULT_DRIFT_TOLERANCE, cli, resolve_drift_tolerance
from wppc.model import build_run_meta, build_weights_snapshot, compare_weights_snapshot

from conftest import EXAMPLE_P, make_segments

_REPO = Path(__file__).resolve().parents[1]
_GOOGLE_CSV = _REPO / "sample_data" / "google_segments.sample.csv"
_GOOGLE_MAPPING = _REPO / "config" / "mapping.google.sample.yaml"


def test_build_weights_snapshot_keys_and_injected_timestamp(example_weights):
    pinned = "2020-01-01T00:00:00+00:00"
    snap = build_weights_snapshot(example_weights, "google", timestamp=pinned)

    assert set(snap.keys()) == {
        "timestamp", "platform", "cm3_order", "repeat_rate", "cm3_repeat",
        "p_vector", "telescope_sum",
    }
    assert snap["timestamp"] == pinned  # used verbatim, no clock read
    assert snap["platform"] == "google"
    assert snap["cm3_order"] == example_weights.cm3_order
    assert snap["repeat_rate"] == example_weights.repeat_rate
    assert snap["cm3_repeat"] == example_weights.cm3_repeat
    assert snap["p_vector"] == EXAMPLE_P
    assert snap["telescope_sum"] == example_weights.telescope_sum
    # JSON-serializable (no exception).
    json.dumps(snap)


def test_compare_flags_component_beyond_tolerance(example_weights):
    base = build_weights_snapshot(example_weights, "google", timestamp="t0")
    cur = copy.deepcopy(base)
    cur["cm3_order"] = base["cm3_order"] * 1.20  # +20% > 15% tolerance

    result = compare_weights_snapshot(cur, base, tolerance=0.15)
    assert result["flagged"] is True
    assert result["baseline_path"] is None  # caller fills it
    assert result["tolerance"] == 0.15
    fields = {m["field"] for m in result["moved"]}
    assert fields == {"cm3_order"}
    moved = result["moved"][0]
    assert moved["from"] == base["cm3_order"]
    assert moved["to"] == cur["cm3_order"]
    assert abs(moved["pct"] - 0.20) < 1e-9


def test_compare_within_tolerance_is_not_flagged(example_weights):
    base = build_weights_snapshot(example_weights, "google", timestamp="t0")
    cur = copy.deepcopy(base)
    cur["repeat_rate"] = base["repeat_rate"] * 1.05  # +5% < 15%

    result = compare_weights_snapshot(cur, base, tolerance=0.15)
    assert result["flagged"] is False
    assert result["moved"] == []


def test_compare_tolerance_respected_as_passed(example_weights):
    base = build_weights_snapshot(example_weights, "google", timestamp="t0")
    cur = copy.deepcopy(base)
    cur["p_vector"]["click"] = base["p_vector"]["click"] * 1.10  # +10% delta

    # Same delta: flagged at a tight 0.05 tolerance, not at a loose 0.50.
    tight = compare_weights_snapshot(cur, base, tolerance=0.05)
    loose = compare_weights_snapshot(cur, base, tolerance=0.50)
    assert tight["flagged"] is True
    assert {m["field"] for m in tight["moved"]} == {"p_vector.click"}
    assert loose["flagged"] is False


def test_compare_pvector_entry_namespaced(example_weights):
    base = build_weights_snapshot(example_weights, "google", timestamp="t0")
    cur = copy.deepcopy(base)
    cur["p_vector"]["engagement"] = base["p_vector"]["engagement"] * 2.0

    result = compare_weights_snapshot(cur, base, tolerance=0.15)
    assert {m["field"] for m in result["moved"]} == {"p_vector.engagement"}


def test_compare_zero_baseline_nonzero_current_flags_with_none_pct(example_weights):
    base = build_weights_snapshot(example_weights, "google", timestamp="t0")
    cur = copy.deepcopy(base)
    base["p_vector"]["click"] = 0.0  # undefined relative change
    cur["p_vector"]["click"] = 0.01

    result = compare_weights_snapshot(cur, base, tolerance=0.15)
    assert result["flagged"] is True
    moved = next(m for m in result["moved"] if m["field"] == "p_vector.click")
    assert moved["pct"] is None
    assert moved["from"] == 0.0
    assert moved["to"] == 0.01


def test_build_run_meta_passes_through_weights_version_and_drift(example_weights):
    """The drift result lands in run-metadata via build_run_meta's kwargs; the
    defaults keep the prior stubbed (None) behaviour."""
    from wppc.score import score

    df = make_segments([
        {"segment_id": "solo", "click": 100, "engagement": 60, "add_to_cart": 20,
         "initiate_checkout": 12, "purchase": 8, "repeats": 3},
    ])
    results = score(df, example_weights)
    snapshot = build_weights_snapshot(example_weights, "google", timestamp="t0")
    drift = {"baseline_path": "b.json", "tolerance": 0.15, "moved": [], "flagged": False}

    meta = build_run_meta(results, example_weights, platform="google",
                          weights_version=snapshot, drift=drift)
    assert meta["weights_version"] == snapshot
    assert meta["drift"] == drift

    # Omitting the kwargs preserves the stubbed None behaviour (default-off).
    bare = build_run_meta(results, example_weights, platform="google")
    assert bare["weights_version"] is None
    assert bare["drift"] is None


def test_resolve_tolerance_cli_over_mapping_over_default():
    # CLI value wins over everything.
    assert resolve_drift_tolerance(0.20, {"drift_tolerance": 0.10}) == 0.20
    # Mapping value wins when no CLI value.
    assert resolve_drift_tolerance(None, {"drift_tolerance": 0.10}) == 0.10
    # Falls through to the built-in default (0.15).
    assert resolve_drift_tolerance(None, {}) == DEFAULT_DRIFT_TOLERANCE
    assert resolve_drift_tolerance(None, None) == DEFAULT_DRIFT_TOLERANCE
    assert DEFAULT_DRIFT_TOLERANCE == 0.15


def test_no_tolerance_literal_in_kernels():
    """The tolerance literal must not appear in the scoring kernels — it lives in
    the CLI-layer default / mapping and is passed down as data."""
    for name in ("score.py", "weights.py"):
        text = (_REPO / "wppc" / name).read_text(encoding="utf-8")
        assert "0.15" not in text, f"{name} must not carry the drift-tolerance literal"


def test_cli_writes_sidecar_without_baseline(tmp_path):
    runner = CliRunner()
    out = tmp_path / "report.xlsx"
    result = runner.invoke(cli, [
        "report", "--platform", "google",
        "--input", str(_GOOGLE_CSV),
        "--mapping", str(_GOOGLE_MAPPING),
        "--output", str(out),
    ])
    assert result.exit_code == 0, result.output
    sidecar = tmp_path / "report.weights.json"
    assert sidecar.exists()
    snap = json.loads(sidecar.read_text())
    assert snap["platform"] == "google"
    assert set(snap.keys()) == {
        "timestamp", "platform", "cm3_order", "repeat_rate", "cm3_repeat",
        "p_vector", "telescope_sum",
    }
    # No baseline -> no drift line emitted.
    assert "DRIFT" not in result.output


def test_cli_warns_on_drift_with_baseline_and_exits_zero(tmp_path):
    runner = CliRunner()
    out = tmp_path / "report.xlsx"

    # First run to produce a genuine sidecar, then doctor a copy as the baseline.
    first = runner.invoke(cli, [
        "report", "--platform", "google",
        "--input", str(_GOOGLE_CSV),
        "--mapping", str(_GOOGLE_MAPPING),
        "--output", str(out),
    ])
    assert first.exit_code == 0, first.output
    snap = json.loads((tmp_path / "report.weights.json").read_text())

    doctored = copy.deepcopy(snap)
    doctored["cm3_order"] = snap["cm3_order"] * 1.30  # +30% > 15% default
    baseline_path = tmp_path / "baseline.weights.json"
    baseline_path.write_text(json.dumps(doctored, indent=2) + "\n")

    out2 = tmp_path / "report2.xlsx"
    second = runner.invoke(cli, [
        "report", "--platform", "google",
        "--input", str(_GOOGLE_CSV),
        "--mapping", str(_GOOGLE_MAPPING),
        "--output", str(out2),
        "--weights-baseline", str(baseline_path),
    ])
    assert second.exit_code == 0, second.output
    assert "WEIGHT DRIFT" in second.output
    assert "cm3_order" in second.output
    # Read-only comparison: the baseline file is untouched.
    assert json.loads(baseline_path.read_text()) == doctored
