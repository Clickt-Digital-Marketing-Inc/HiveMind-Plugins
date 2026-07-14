#!/usr/bin/env python3
"""Node-vs-Python parity for THIS skill's js_kernel (bidding_spec.JS_KERNEL).

Computes bidding_core.classify_row expected outputs on the fixture's rows
across several param scenarios (default + two tuned variants exercising
different mismatch branches), then shells out to `node js_kernel_parity.mjs`
to replay the same rows/params through the JS kernel and assert equality.

    python3 tests/js_kernel_parity.py

Dev-only — requires `node` on PATH (no npm packages needed; unlike the shared
tuner harness this script needs no jsdom). Exit 0 = pass, 1 = a failure or
node missing (reported, not silently skipped).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE.parents[2] / "_shared"))

import bidding_core as core   # noqa: E402
import bidding_spec as spec_mod  # noqa: E402

FIXTURE = HERE / "sample-findings.json"

_FIELDS = ("maturity_score", "recommended_tier", "tier_gap", "mismatch", "severity")


def _expected(universe_rows, params):
    classified = core.classify(universe_rows, params)
    return [{k: r[k] for k in _FIELDS} for r in classified]


def main() -> int:
    node = shutil.which("node")
    if not node:
        sys.stderr.write("ERROR: node not found on PATH — install Node to run this parity check\n")
        return 1

    findings = core.load_findings(str(FIXTURE))
    model = core.compute_model(findings)
    universe = model["_universe"]
    default_params = model["params"]

    tuned_gate = dict(default_params); tuned_gate["conv_gate"] = 15.0
    tuned_bands = dict(default_params)
    tuned_bands["band_edge_1"], tuned_bands["band_edge_2"] = 20.0, 40.0
    tuned_bands["tier_gap_threshold"] = 0.5

    scenarios = [
        {"name": "default params", "params": default_params,
         "expected": _expected(universe, default_params)},
        {"name": "tuned conv_gate (30 -> 15)", "params": tuned_gate,
         "expected": _expected(universe, tuned_gate)},
        {"name": "tuned bands + tighter tier-gap threshold", "params": tuned_bands,
         "expected": _expected(universe, tuned_bands)},
    ]

    rows = spec_mod.html_embed(model)["rows"]  # exactly what the real explorer embeds

    fixture = {"kernel_src": spec_mod.JS_KERNEL, "rows": rows, "scenarios": scenarios}
    with tempfile.TemporaryDirectory() as td:
        fx_path = Path(td) / "fixture.json"
        fx_path.write_text(json.dumps(fixture))
        r = subprocess.run([node, str(HERE / "js_kernel_parity.mjs"), str(fx_path)],
                           capture_output=True, text=True)
        print(r.stdout)
        if r.returncode != 0:
            sys.stderr.write(r.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
