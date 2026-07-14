#!/usr/bin/env python3
"""Node-vs-Python parity for THIS skill's js_kernel (conv_tracking_spec.JS_KERNEL).

Computes conv_tracking_core.classify_trend/summarize_trend expected outputs on
the fixture's rows across several param scenarios (default + three tuned
variants exercising different flag branches), then shells out to
`node js_kernel_parity.mjs` to replay the same rows/params through the JS
kernel's `classify`/`summarize` and assert equality (flags, score, tier per
row; campaigns/scored/no_benchmark/critical/high/watch/clean/
landing_page_suspect from summarize()).

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

import conv_tracking_core as core   # noqa: E402
import conv_tracking_spec as spec_mod  # noqa: E402

FIXTURE = HERE / "sample-findings.json"

_ROW_FIELDS = ("flags", "score", "tier")
_SUMMARY_FIELDS = ("campaigns", "scored", "no_benchmark", "critical", "high",
                   "watch", "clean", "landing_page_suspect")


def _expected_rows(universe_rows, params):
    classified = core.classify_trend(universe_rows, params)
    return [{k: r[k] for k in _ROW_FIELDS} for r in classified]


def _expected_summary(universe_rows, params):
    classified = core.classify_trend(universe_rows, params)
    s = core.summarize_trend(classified)
    return {k: s[k] for k in _SUMMARY_FIELDS}


def main() -> int:
    node = shutil.which("node")
    if not node:
        sys.stderr.write("ERROR: node not found on PATH — install Node to run this parity check\n")
        return 1

    findings = core.load_findings(str(FIXTURE))
    model = core.compute_model(findings)
    universe = core.build_trend_universe(findings["campaign_trend"])
    default_params = model["params"]

    # Tuned variant 1: loosen the CVR-drop threshold — moves the cvr_drop /
    # landing_page_suspect branch (fewer campaigns qualify at 30% -> 15%... in
    # this direction MORE qualify since the bar to flag is easier to clear).
    tuned_drop = dict(default_params)
    tuned_drop["cvr_drop_pct"] = 0.15

    # Tuned variant 2: raise the volume floor and require CTR to improve (not
    # just hold) — exercises thin_volume and ctr_held_or_up together.
    tuned_volume_ctr = dict(default_params)
    tuned_volume_ctr["min_conv_30d"] = 50.0
    tuned_volume_ctr["ctr_factor"] = 1.20

    # Tuned variant 3: relax the below-account-CVR factor — moves the
    # below_account_cvr branch independently of the other three rules.
    tuned_cvr_factor = dict(default_params)
    tuned_cvr_factor["cvr_factor"] = 0.90

    scenarios = [
        {"name": "default params", "params": default_params,
         "expected": _expected_rows(universe, default_params),
         "expected_summary": _expected_summary(universe, default_params)},
        {"name": "tuned cvr_drop_pct (30% -> 15%)", "params": tuned_drop,
         "expected": _expected_rows(universe, tuned_drop),
         "expected_summary": _expected_summary(universe, tuned_drop)},
        {"name": "tuned min_conv_30d (30 -> 50) + ctr_factor (1.00 -> 1.20)",
         "params": tuned_volume_ctr,
         "expected": _expected_rows(universe, tuned_volume_ctr),
         "expected_summary": _expected_summary(universe, tuned_volume_ctr)},
        {"name": "tuned cvr_factor (0.50 -> 0.90)", "params": tuned_cvr_factor,
         "expected": _expected_rows(universe, tuned_cvr_factor),
         "expected_summary": _expected_summary(universe, tuned_cvr_factor)},
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
